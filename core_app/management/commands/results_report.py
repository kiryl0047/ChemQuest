"""
python manage.py results_report

Read-only snapshot of the ChemQuest database for the "Results and Validation"
section of project documentation. It never writes to the database and never
prints usernames, emails, or other personally identifying data.

Usage:
    python manage.py results_report
    python manage.py results_report --format json
    python manage.py results_report --format markdown --output results.md
    python manage.py results_report --format both --output results

The command reads whichever database Django is configured for, so production
data is reported by running it with DATABASE_URL set.
"""
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from core_app.models import (
    PartProgress,
    ProblemPart,
    ProblemProgress,
    StoichiometryProblem,
    StudentTelemetryLog,
    Substance,
    SynthesisAttempt,
    UserProfile,
    CONVERSION_CHOICES,
    NODE_COUNT,
    XP_PER_LEVEL,
)
from core_app.views import (
    CONVERSION_TYPE_LABELS,
    LANE_TOLERANCE,
    SYNTHESIS_ELIGIBILITY_COUNT,
)

# Telemetry uses these pseudo part labels for Module 1 / Module 3 events that
# are not attached to a ProblemPart row.
PSEUDO_PART_LABELS = {
    'checkpoint', 'balance', 'molar_mass', 'comparison', 'deduction',
}

CONVERSION_LABELS = dict(CONVERSION_CHOICES)


# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------

def _mean(values):
    return round(sum(values) / len(values), 1) if values else None


def _share(numerator, denominator):
    if not denominator:
        return '—'
    return f'{numerator} of {denominator} ({numerator / denominator * 100:.1f}%)'


def _server_version(connection):
    if connection.vendor != 'postgresql':
        return None
    version = connection.pg_version
    return f'{version // 10000}.{version % 10000}'


def _median(values):
    return round(statistics.median(values), 1) if values else None


def _table(headers, rows):
    lines = [
        '| ' + ' | '.join(headers) + ' |',
        '|' + '|'.join('---' for _ in headers) + '|',
    ]
    for row in rows:
        lines.append('| ' + ' | '.join(str(cell) for cell in row) + ' |')
    return '\n'.join(lines)


def _status(condition, warn_is_fail=False):
    if condition:
        return 'PASS'
    return 'FAIL' if warn_is_fail else 'WARN'


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def _collect(now):
    catalog = list(
        StoichiometryProblem.objects.filter(is_generated=False).order_by('problem_id')
    )
    generated = list(
        StoichiometryProblem.objects.filter(is_generated=True).order_by('problem_id')
    )
    catalog_ids = {p.problem_id for p in catalog}
    generated_ids = {p.problem_id for p in generated}

    parts = list(
        ProblemPart.objects
        .select_related('problem', 'given_substance', 'target_substance')
        .order_by('problem__problem_id', 'order')
    )
    catalog_parts = [p for p in parts if p.problem.problem_id in catalog_ids]
    parts_by_problem = defaultdict(list)
    for part in catalog_parts:
        parts_by_problem[part.problem.problem_id].append(part)
    part_pairs = {(p.problem.problem_id, p.part_label) for p in catalog_parts}

    progress = list(ProblemProgress.objects.all())
    part_progress = list(PartProgress.objects.all())
    logs = list(StudentTelemetryLog.objects.all().order_by('created_at'))
    attempts = list(SynthesisAttempt.objects.all().order_by('created_at'))
    profiles = list(UserProfile.objects.select_related('user'))

    users = User.objects.count()
    active_user_ids = (
        {row.user_id for row in progress}
        | {row.user_id for row in part_progress}
        | {row.user_id for row in logs if row.user_id}
        | {row.user_id for row in attempts}
    )

    # ---------------------------------------------------------------- funnel
    progress_by_user = defaultdict(dict)
    for row in progress:
        progress_by_user[row.user_id][row.problem_id] = row

    lanes_by_user_problem = defaultdict(set)
    for row in part_progress:
        if row.lane_cleared:
            lanes_by_user_problem[(row.user_id, row.problem_id)].add(row.part_label)

    problem_map = {p.problem_id: p for p in catalog}
    m1_rows = 0
    m1_users = set()
    lanes_rows = 0
    lanes_users = set()
    strict_rows = 0
    strict_users = set()
    m3_rows = 0
    m3_users = set()

    for row in progress:
        problem = problem_map.get(row.problem_id)
        if problem is None:
            continue
        m1_done = row.balancing_cleared and row.molar_mass_cleared
        if m1_done:
            m1_rows += 1
            m1_users.add(row.user_id)
        expected_lanes = {p.part_label for p in parts_by_problem[problem.problem_id]}
        cleared = lanes_by_user_problem.get((row.user_id, row.problem_id), set())
        lanes_done = bool(expected_lanes) and expected_lanes <= cleared
        if lanes_done:
            lanes_rows += 1
            lanes_users.add(row.user_id)
        if problem.is_limiting_problem and row.deduction_cleared:
            m3_rows += 1
            m3_users.add(row.user_id)
        if m1_done and lanes_done and (row.deduction_cleared or not problem.is_limiting_problem):
            strict_rows += 1
            strict_users.add(row.user_id)

    completed_by_user = Counter()
    for row in progress:
        problem = problem_map.get(row.problem_id)
        if problem is None:
            continue
        if row.is_completed(problem):
            completed_by_user[row.user_id] += 1

    unlocked_users = {
        user_id for user_id, count in completed_by_user.items()
        if count >= SYNTHESIS_ELIGIBILITY_COUNT
    }
    synthesis_users = {row.user_id for row in attempts}

    # ------------------------------------------------------- problem results
    logs_by_problem = defaultdict(list)
    for log in logs:
        logs_by_problem[log.problem_id].append(log)

    problem_rows = []
    for problem in catalog:
        pid = problem.problem_id
        learners = {row.user_id for row in progress if row.problem_id == pid}
        learners |= {uid for (uid, p_id) in lanes_by_user_problem if p_id == pid}
        learners |= {log.user_id for log in logs_by_problem[pid] if log.user_id}
        expected_lanes = {p.part_label for p in parts_by_problem[pid]}
        lanes_complete = sum(
            1 for (uid, p_id), cleared in lanes_by_user_problem.items()
            if p_id == pid and expected_lanes and expected_lanes <= cleared
        )
        m1_here = sum(
            1 for row in progress
            if row.problem_id == pid
            and row.balancing_cleared and row.molar_mass_cleared
        )
        strict_here = sum(
            1 for row in progress
            if row.problem_id == pid
            and row.balancing_cleared and row.molar_mass_cleared
            and expected_lanes <= lanes_by_user_problem.get((row.user_id, pid), set())
            and (row.deduction_cleared or not problem.is_limiting_problem)
        )
        problem_logs = logs_by_problem[pid]
        verified = sum(1 for log in problem_logs if log.is_correct)
        failed = sum(log.attempts_count for log in problem_logs)
        problem_rows.append({
            'problem_id': pid,
            'title': problem.title,
            'kind': 'Limiting' if problem.is_limiting_problem else 'Standard',
            'parts': len(parts_by_problem[pid]),
            'learners': len(learners),
            'm1_complete': m1_here,
            'lanes_complete': lanes_complete,
            'strict_complete': strict_here,
            'logs': len(problem_logs),
            'accuracy': round(verified / (verified + failed) * 100, 1)
            if verified + failed else None,
        })

    # --------------------------------------------------------- accuracy data
    part_type = {
        (p.problem.problem_id, p.part_label): p.conversion_type
        for p in catalog_parts
    }

    overall_verified = sum(1 for log in logs if log.is_correct)
    overall_failed = sum(log.attempts_count for log in logs)
    overall_accuracy = round(
        overall_verified / (overall_verified + overall_failed) * 100, 1
    ) if overall_verified + overall_failed else None

    type_stats = {
        ct: {'verified': 0, 'failed': 0, 'entries': 0}
        for ct in CONVERSION_TYPE_LABELS
    }
    for log in logs:
        ctype = part_type.get((log.problem_id, log.part_label))
        if not ctype:
            continue
        bucket = type_stats.setdefault(
            ctype, {'verified': 0, 'failed': 0, 'entries': 0})
        bucket['entries'] += 1
        bucket['failed'] += log.attempts_count
        if log.is_correct:
            bucket['verified'] += 1

    phase_stats = defaultdict(lambda: {'verified': 0, 'failed': 0, 'entries': 0})
    substep_stats = defaultdict(lambda: {'verified': 0, 'failed': 0, 'entries': 0})
    for log in logs:
        for bucket in (phase_stats[log.module_phase], substep_stats[log.sub_step or '—']):
            bucket['entries'] += 1
            bucket['failed'] += log.attempts_count
            if log.is_correct:
                bucket['verified'] += 1

    # ------------------------------------------------------- stage flag counts
    stage_flags = []
    for field, label in [
        ('checkpoint_cleared', 'Predict checkpoint'),
        ('balancing_cleared', 'Balancing verified (1A)'),
        ('molar_mass_cleared', 'Molar masses verified (1B)'),
        ('exit_checkpoint_cleared', 'Exit checkpoint'),
        ('yield_comparison_verified', 'Yield comparison'),
        ('deduction_cleared', 'Limiting deduction'),
        ('synthesis_passed', 'Synthesis passed'),
    ]:
        rows = [row for row in progress if getattr(row, field)]
        stage_flags.append({
            'field': field,
            'label': label,
            'rows': len(rows),
            'users': len({row.user_id for row in rows}),
        })

    # ------------------------------------------------------------- timeline
    weekly = Counter()
    for log in logs:
        iso = log.created_at.isocalendar()
        weekly[(iso[0], iso[1])] += 1

    # ------------------------------------------------------------ validations
    validations = []

    executor = MigrationExecutor(connection)
    pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
    validations.append({
        'id': 'schema.current',
        'check': 'Django migrations applied',
        'expected': 'No unapplied migrations',
        'observed': f'{len(pending)} pending' if pending else '0 pending',
        'status': _status(not pending, warn_is_fail=True),
        'note': '' if not pending else ', '.join(
            f'{migration.app_label}.{migration.name}' for migration, _ in pending),
    })

    bad_payloads = []
    for problem in catalog:
        try:
            reactants = problem.reactants
            products = problem.products
            coefficients = [int(x) for x in problem.correct_coefficients.split(',')]
            if not reactants or not products or not coefficients:
                bad_payloads.append(problem.problem_id)
        except (TypeError, ValueError):
            bad_payloads.append(problem.problem_id)
    validations.append({
        'id': 'catalog.payloads',
        'check': 'Reaction payloads parse',
        'expected': f'{len(catalog)} valid problems',
        'observed': f'{len(catalog) - len(bad_payloads)} valid',
        'status': _status(not bad_payloads, warn_is_fail=True),
        'note': ', '.join(bad_payloads[:5]),
    })

    unresolved = []
    for part in catalog_parts:
        try:
            formulas = {e['formula'] for e in part.problem.reactants + part.problem.products}
        except (TypeError, ValueError):
            unresolved.append(f'{part.problem.problem_id}/{part.part_label}')
            continue
        if (part.given_substance.formula not in formulas
                or part.target_substance.formula not in formulas):
            unresolved.append(f'{part.problem.problem_id}/{part.part_label}')
    validations.append({
        'id': 'catalog.substances',
        'check': 'Part substances appear in the reaction',
        'expected': f'{len(catalog_parts)} parts',
        'observed': f'{len(catalog_parts) - len(unresolved)} resolved',
        'status': _status(not unresolved, warn_is_fail=True),
        'note': ', '.join(unresolved[:5]),
    })

    invalid_types = [p for p in catalog_parts if p.conversion_type not in NODE_COUNT]
    validations.append({
        'id': 'catalog.conversion_types',
        'check': 'Conversion types are known',
        'expected': ', '.join(CONVERSION_TYPE_LABELS),
        'observed': f'{len(invalid_types)} invalid',
        'status': _status(not invalid_types, warn_is_fail=True),
        'note': '',
    })

    answer_deltas = []
    for part in catalog_parts:
        try:
            value = float(part.given_quantity)
            for node in part.expected_nodes():
                value *= node['num_value'] / node['den_value']
            delta = abs(value - float(part.correct_answer))
            answer_deltas.append((part, value, delta))
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            answer_deltas.append((part, None, float('inf')))
    answer_bad = [row for row in answer_deltas if row[2] > LANE_TOLERANCE]
    answer_max = max((row[2] for row in answer_deltas if row[2] != float('inf')), default=0.0)
    answer_max_pct = max(
        (delta / float(part.correct_answer) * 100
         for part, _value, delta in answer_bad if part.correct_answer),
        default=0.0,
    )
    validations.append({
        'id': 'grading.answers',
        'check': 'Stored answers match node recomputation',
        'expected': f'Within ±{LANE_TOLERANCE}',
        'observed': f'{len(catalog_parts) - len(answer_bad)}/{len(catalog_parts)} within tolerance '
                    f'(max Δ {answer_max:.4f})',
        'status': 'WARN' if answer_bad else 'PASS',
        'note': '; '.join(
            f'{part.problem.problem_id}/{part.part_label} Δ{delta:.4f}'
            for part, _value, delta in answer_bad[:5]),
    })

    dup_progress = len(progress) - len({(row.user_id, row.problem_id) for row in progress})
    dup_part = len(part_progress) - len(
        {(row.user_id, row.problem_id, row.part_label) for row in part_progress})
    validations.append({
        'id': 'progress.unique',
        'check': 'Progress rows are unique per learner/item',
        'expected': '0 duplicates',
        'observed': f'{dup_progress} progress, {dup_part} lane duplicates',
        'status': _status(not dup_progress and not dup_part, warn_is_fail=True),
        'note': '',
    })

    orphan_progress = [row for row in progress if row.problem_id not in catalog_ids]
    orphan_lanes = [
        row for row in part_progress
        if (row.problem_id, row.part_label) not in part_pairs
    ]
    validations.append({
        'id': 'progress.references',
        'check': 'Progress references catalog problems/parts',
        'expected': '0 orphan rows',
        'observed': f'{len(orphan_progress)} progress, {len(orphan_lanes)} lane orphans',
        'status': _status(not orphan_progress and not orphan_lanes, warn_is_fail=True),
        'note': '',
    })

    bad_telemetry = []
    for log in logs:
        if log.problem_id not in catalog_ids:
            bad_telemetry.append(log)
        elif log.part_label not in PSEUDO_PART_LABELS and (
                log.problem_id, log.part_label) not in part_pairs:
            bad_telemetry.append(log)
    validations.append({
        'id': 'telemetry.references',
        'check': 'Telemetry references known problems/parts',
        'expected': f'{len(logs)} valid rows',
        'observed': f'{len(logs) - len(bad_telemetry)} valid',
        'status': _status(not bad_telemetry),
        'note': f'{len(bad_telemetry)} unmatched' if bad_telemetry else '',
    })

    leakage = (
        ProblemProgress.objects.filter(problem_id__in=generated_ids).count()
        + PartProgress.objects.filter(problem_id__in=generated_ids).count()
        + StudentTelemetryLog.objects.filter(problem_id__in=generated_ids).count()
    )
    validations.append({
        'id': 'synthesis.isolation',
        'check': 'Generated problems stay out of student records',
        'expected': '0 references',
        'observed': f'{leakage} references',
        'status': _status(leakage == 0, warn_is_fail=True),
        'note': '',
    })

    bad_attempts = []
    for attempt in attempts:
        expected_score = round(attempt.correct_items / attempt.total_items * 100, 1) \
            if attempt.total_items else 0.0
        if (abs(expected_score - attempt.score_pct) > 0.05
                or attempt.correct_items > attempt.total_items
                or not 0 <= attempt.score_pct <= 100):
            bad_attempts.append(attempt)
    validations.append({
        'id': 'synthesis.scores',
        'check': 'Synthesis scores are internally consistent',
        'expected': f'{len(attempts)} consistent record(s)',
        'observed': f'{len(attempts) - len(bad_attempts)} consistent',
        'status': _status(not bad_attempts),
        'note': '',
    })

    negative_attempts = sum(1 for log in logs if log.attempts_count < 0)
    negative_xp = sum(1 for profile in profiles if profile.total_xp < 0)
    validations.append({
        'id': 'counters.non_negative',
        'check': 'Attempt and XP counters are non-negative',
        'expected': '0 negative values',
        'observed': f'{negative_attempts} attempts, {negative_xp} profiles',
        'status': _status(negative_attempts == 0 and negative_xp == 0, warn_is_fail=True),
        'note': '',
    })

    future_logs = [log for log in logs if log.created_at > now]
    validations.append({
        'id': 'events.chronology',
        'check': 'No future-dated telemetry',
        'expected': '0 rows',
        'observed': f'{len(future_logs)} rows',
        'status': _status(not future_logs),
        'note': '',
    })

    premature = [
        row for row in progress
        if (row.deduction_cleared or row.yield_comparison_verified)
        and not (row.balancing_cleared and row.molar_mass_cleared)
    ]
    legacy_exit = [
        row for row in progress
        if row.exit_checkpoint_cleared and not row.checkpoint_cleared
    ]
    legacy_balance = [
        row for row in progress
        if row.balancing_cleared and not row.checkpoint_cleared
    ]
    validations.append({
        'id': 'progress.sequencing',
        'check': 'Later stages imply earlier gates',
        'expected': '0 out-of-order rows',
        'observed': f'{len(premature) + len(legacy_exit) + len(legacy_balance)} row(s)',
        'status': 'WARN' if (premature or legacy_exit or legacy_balance) else 'PASS',
        'note': (
            f'{len(legacy_balance)} balancing row(s) predate the predict checkpoint; '
            f'{len(premature)} dependency violation(s)'
        ),
    })

    lanes_without_chain = [
        row for row in part_progress if row.lane_cleared and not row.chain_json
    ]
    validations.append({
        'id': 'lanes.history',
        'check': 'Cleared lanes retain a verified chain',
        'expected': '0 empty chains',
        'observed': f'{len(lanes_without_chain)} empty',
        'status': _status(not lanes_without_chain, warn_is_fail=True),
        'note': '',
    })

    covered_types = {p.conversion_type for p in catalog_parts}
    validations.append({
        'id': 'catalog.coverage',
        'check': 'All conversion types are represented',
        'expected': f'{len(CONVERSION_TYPE_LABELS)} types',
        'observed': f'{len(covered_types & set(CONVERSION_TYPE_LABELS))} types',
        'status': _status(set(CONVERSION_TYPE_LABELS) <= covered_types),
        'note': ', '.join(sorted(set(CONVERSION_TYPE_LABELS) - covered_types)),
    })

    # --------------------------------------------------------------- synthesis
    synthesis_scores = [attempt.score_pct for attempt in attempts]
    latest_by_user = {}
    for attempt in attempts:
        latest_by_user[attempt.user_id] = attempt

    # ---------------------------------------------------------------- xp data
    xp_values = [profile.total_xp for profile in profiles]
    levels = Counter(profile.level for profile in profiles)

    return {
        'generated_at': now.isoformat(),
        'source': {
            'engine': connection.vendor,
            'database': connection.settings_dict.get('NAME'),
            'server_version': _server_version(connection),
            'django': _django_version(),
        },
        'inventory': [
            {'label': 'Registered accounts', 'count': users},
            {'label': 'User profiles', 'count': len(profiles)},
            {'label': 'Catalog problems', 'count': len(catalog)},
            {'label': 'Generated synthesis problems', 'count': len(generated)},
            {'label': 'Limiting-reagent problems (catalog)', 'count': sum(
                1 for p in catalog if p.is_limiting_problem)},
            {'label': 'Problem parts (catalog)', 'count': len(catalog_parts)},
            {'label': 'Substances', 'count': Substance.objects.count()},
            {'label': 'ProblemProgress rows', 'count': len(progress)},
            {'label': 'PartProgress rows', 'count': len(part_progress)},
            {'label': 'Telemetry rows', 'count': len(logs)},
            {'label': 'Synthesis attempts', 'count': len(attempts)},
        ],
        'activity_window': {
            'first': logs[0].created_at.isoformat() if logs else None,
            'last': logs[-1].created_at.isoformat() if logs else None,
        },
        'engagement': {
            'accounts': users,
            'active_accounts': len(active_user_ids),
            'telemetry_accounts': len({log.user_id for log in logs if log.user_id}),
            'progress_accounts': len({row.user_id for row in progress}),
            'progress_rows': len(progress),
            'lane_accounts': len({row.user_id for row in part_progress}),
            'lane_rows': sum(1 for row in part_progress if row.lane_cleared),
            'synthesis_accounts': len(synthesis_users),
            'm1_complete_accounts': len(m1_users),
            'm1_complete_rows': m1_rows,
            'lanes_complete_accounts': len(lanes_users),
            'lanes_complete_rows': lanes_rows,
            'limiting_accounts': len(m3_users),
            'limiting_rows': m3_rows,
            'strict_complete_accounts': len(strict_users),
            'strict_complete_rows': strict_rows,
            'synthesis_unlocked_accounts': len(unlocked_users),
        },
        'stage_flags': stage_flags,
        'conversion_mix': [
            {
                'type': ctype,
                'label': CONVERSION_LABELS.get(ctype, ctype),
                'nodes': NODE_COUNT.get(ctype),
                'parts': sum(1 for p in catalog_parts if p.conversion_type == ctype),
            }
            for ctype in CONVERSION_TYPE_LABELS
        ],
        'problem_results': problem_rows,
        'accuracy': {
            'verified': overall_verified,
            'failed': overall_failed,
            'overall': overall_accuracy,
            'by_type': [
                {
                    'type': ctype,
                    'entries': type_stats[ctype]['entries'],
                    'verified': type_stats[ctype]['verified'],
                    'failed': type_stats[ctype]['failed'],
                    'accuracy': round(
                        type_stats[ctype]['verified']
                        / (type_stats[ctype]['verified'] + type_stats[ctype]['failed']) * 100, 1
                    ) if type_stats[ctype]['verified'] + type_stats[ctype]['failed'] else None,
                }
                for ctype in CONVERSION_TYPE_LABELS
            ],
            'by_phase': [
                {
                    'phase': phase,
                    'entries': bucket['entries'],
                    'verified': bucket['verified'],
                    'failed': bucket['failed'],
                    'accuracy': round(
                        bucket['verified'] / (bucket['verified'] + bucket['failed']) * 100, 1
                    ) if bucket['verified'] + bucket['failed'] else None,
                }
                for phase, bucket in sorted(phase_stats.items())
            ],
            'by_substep': [
                {
                    'sub_step': substep,
                    'entries': bucket['entries'],
                    'verified': bucket['verified'],
                    'failed': bucket['failed'],
                    'accuracy': round(
                        bucket['verified'] / (bucket['verified'] + bucket['failed']) * 100, 1
                    ) if bucket['verified'] + bucket['failed'] else None,
                }
                for substep, bucket in sorted(
                    substep_stats.items(), key=lambda item: str(item[0]))
            ],
        },
        'synthesis': {
            'attempts': len(attempts),
            'passed': sum(1 for attempt in attempts if attempt.passed),
            'mean_score': _mean(synthesis_scores),
            'median_score': _median(synthesis_scores),
            'best_score': round(max(synthesis_scores), 1) if synthesis_scores else None,
            'unlocked_accounts': len(unlocked_users),
            'attempting_accounts': len(synthesis_users),
            'attempt_rows': [
                {
                    'score_pct': round(attempt.score_pct, 1),
                    'correct_items': attempt.correct_items,
                    'total_items': attempt.total_items,
                    'passed': attempt.passed,
                    'created_at': attempt.created_at.isoformat(),
                }
                for attempt in attempts
            ],
        },
        'xp': {
            'total': sum(xp_values),
            'mean': _mean(xp_values),
            'median': _median(xp_values),
            'max': max(xp_values) if xp_values else None,
            'earned_accounts': sum(1 for value in xp_values if value > 0),
            'levels': [
                {'level': level, 'accounts': count}
                for level, count in sorted(levels.items())
            ],
        },
        'timeline': [
            {'iso_year': year, 'iso_week': week, 'events': count}
            for (year, week), count in sorted(weekly.items())
        ],
        'validations': validations,
        'diagnostics': {
            'answer_outlier_max_pct': round(answer_max_pct, 4),
            'answer_outliers': [
                {
                    'problem_id': part.problem.problem_id,
                    'part_label': part.part_label,
                    'recomputed': round(value, 4) if value is not None else None,
                    'stored': float(part.correct_answer),
                    'delta': round(delta, 4) if delta != float('inf') else None,
                }
                for part, value, delta in answer_bad
            ],
        },
    }


def _django_version():
    import django
    return django.get_version()


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _render_markdown(report):
    source = report['source']
    inv = report['inventory']
    engagement = report['engagement']
    lines = [
        '# ChemQuest — Results and Validation',
        '',
        f'**Generated:** {report["generated_at"]}  ',
        f'**Database:** {source["database"]} ({source["engine"]}'
        + (f' {source["server_version"]}' if source['server_version'] else '') + ')  ',
        f'**Django:** {source["django"]}  ',
        '**Scope:** read-only snapshot of all rows at generation time. '
        'No personally identifying data is included.',
        '',
        '## 1. Activity window',
        '',
        _table(
            ['Property', 'Value'],
            [
                ['First telemetry event',
                 report['activity_window']['first'] or '—'],
                ['Last telemetry event',
                 report['activity_window']['last'] or '—'],
                ['Registered accounts', engagement['accounts']],
                ['Accounts with recorded activity', engagement['active_accounts']],
            ],
        ),
        '',
        '## 2. Headline results',
        '',
        _table(
            ['Metric', 'Value'],
            [
                ['Catalog problems', len(report['problem_results'])],
                ['Active accounts (of registered)',
                 _share(engagement['active_accounts'], engagement['accounts'])],
                ['Completed Module 1 (of active accounts)',
                 _share(engagement['m1_complete_accounts'], engagement['active_accounts'])],
                ['Cleared every lane for at least one problem (of active)',
                 _share(engagement['lanes_complete_accounts'], engagement['active_accounts'])],
                ['Completed every required stage (strict)',
                 f'{engagement["strict_complete_accounts"]} accounts · '
                 f'{engagement["strict_complete_rows"]} learner-problem rows'],
                ['Overall accuracy',
                 f'{report["accuracy"]["overall"]}% '
                 f'({report["accuracy"]["verified"]} verified ÷ '
                 f'{report["accuracy"]["verified"] + report["accuracy"]["failed"]} submissions)'],
                ['Synthesis attempts',
                 f'{report["synthesis"]["attempts"]} attempted · '
                 f'{report["synthesis"]["passed"]} passed'],
                ['Median XP per account',
                 report['xp']['median'] if report['xp']['median'] is not None else '—'],
            ],
        ),
        '',
        '## 3. Dataset inventory',
        '',
        _table(['Dataset', 'Records'], [[row['label'], row['count']] for row in inv]),
        '',
        '## 4. Validation checks',
        '',
    ]

    rows = []
    for index, check in enumerate(report['validations'], start=1):
        rows.append([
            index, check['check'], check['expected'],
            check['observed'], check['status'],
        ])
    lines.append(_table(['#', 'Check', 'Expected', 'Observed', 'Status'], rows))
    counts = Counter(check['status'] for check in report['validations'])
    lines += [
        '',
        f'**Summary:** {counts.get("PASS", 0)} PASS · '
        f'{counts.get("WARN", 0)} WARN · {counts.get("FAIL", 0)} FAIL',
    ]
    notes = [check for check in report['validations'] if check['note']]
    if notes:
        lines += ['', 'Notes:']
        for check in notes:
            lines.append(f'- **{check["check"]}:** {check["note"]}')

    lines += [
        '',
        '## 5. Engagement funnel',
        '',
        _table(
            ['Stage', 'Accounts', 'Learner-problem rows'],
            [
                ['Accounts with any activity',
                 engagement['active_accounts'], '—'],
                ['Opened the Preparation Ledger (any progress row)',
                 engagement['progress_accounts'], engagement['progress_rows']],
                ['Completed Module 1 (balancing + molar masses)',
                 engagement['m1_complete_accounts'], engagement['m1_complete_rows']],
                ['Cleared at least one Step-Grid lane',
                 engagement['lane_accounts'], engagement['lane_rows']],
                ['Cleared every Step-Grid lane for a problem',
                 engagement['lanes_complete_accounts'], engagement['lanes_complete_rows']],
                ['Verified a limiting-reagent deduction',
                 engagement['limiting_accounts'], engagement['limiting_rows']],
                ['Completed every required stage (strict completion)',
                 engagement['strict_complete_accounts'], engagement['strict_complete_rows']],
                [f'Synthesis unlocked ({SYNTHESIS_ELIGIBILITY_COUNT} completed problems)',
                 engagement['synthesis_unlocked_accounts'], '—'],
                ['Synthesis attempted',
                 engagement['synthesis_accounts'], report['synthesis']['attempts']],
            ],
        ),
        '',
        '## 6. Stage-level results',
        '',
        '### Module 1 — Preparation Ledger',
        '',
        _table(
            ['Gate', 'Rows', 'Accounts'],
            [[row['label'], row['rows'], row['users']] for row in report['stage_flags']],
        ),
        '',
        '### Module 2 — Step-Grid Workspace',
        '',
        _table(
            ['Conversion type', 'Nodes', 'Catalog parts', 'Entries', 'Verified', 'Failed attempts', 'Accuracy'],
            [
                [row['label'], row['nodes'], row['parts'], next(
                    (a for a in report['accuracy']['by_type'] if a['type'] == row['type']),
                    {}).get('entries', 0), next(
                    (a for a in report['accuracy']['by_type'] if a['type'] == row['type']),
                    {}).get('verified', 0), next(
                    (a for a in report['accuracy']['by_type'] if a['type'] == row['type']),
                    {}).get('failed', 0), next(
                    (a for a in report['accuracy']['by_type'] if a['type'] == row['type']),
                    {}).get('accuracy') or '—']
                for row in report['conversion_mix']
            ],
        ),
        '',
        '### Module 3 — Limiting Reagent',
        '',
        f'- Limiting-reagent problems in catalog: '
        f'**{next((row["count"] for row in inv if row["label"].startswith("Limiting")), 0)}**',
        f'- Accounts with a verified yield comparison: '
        f'**{next((row["users"] for row in report["stage_flags"] if row["field"] == "yield_comparison_verified"), 0)}**',
        f'- Accounts with a verified deduction: **{engagement["limiting_accounts"]}**',
        '',
        '### Synthesis Challenge',
        '',
        f'- Accounts unlocked: **{report["synthesis"]["unlocked_accounts"]}** '
        f'(threshold: {SYNTHESIS_ELIGIBILITY_COUNT} completed problems)',
        f'- Accounts attempted: **{report["synthesis"]["attempting_accounts"]}**',
        f'- Attempts: **{report["synthesis"]["attempts"]}** · '
        f'passed: **{report["synthesis"]["passed"]}**',
        f'- Mean score: **{report["synthesis"]["mean_score"] if report["synthesis"]["mean_score"] is not None else "—"}** · '
        f'median: **{report["synthesis"]["median_score"] if report["synthesis"]["median_score"] is not None else "—"}** · '
        f'best: **{report["synthesis"]["best_score"] if report["synthesis"]["best_score"] is not None else "—"}**',
    ]

    if report['synthesis']['attempt_rows']:
        lines += [
            '',
            _table(
                ['Score %', 'Correct', 'Total', 'Passed', 'Recorded (UTC)'],
                [[row['score_pct'], row['correct_items'], row['total_items'],
                  'Yes' if row['passed'] else 'No', row['created_at']]
                 for row in report['synthesis']['attempt_rows']],
            ),
        ]

    lines += [
        '',
        '## 7. Problem-level results',
        '',
        _table(
            ['Problem', 'Type', 'Parts', 'Learners', 'M1 ✓', 'All lanes ✓', 'Strict ✓', 'Logs', 'Accuracy'],
            [
                [row['problem_id'], row['kind'], row['parts'], row['learners'],
                 row['m1_complete'], row['lanes_complete'], row['strict_complete'],
                 row['logs'], f'{row["accuracy"]}%' if row['accuracy'] is not None else '—']
                for row in report['problem_results']
            ],
        ),
        '',
        '## 8. Accuracy',
        '',
        'Accuracy uses the application formula: verified submissions ÷ '
        '(failed attempts + verified submissions). A verified submission is one row '
        'stored with `is_correct = true`; `attempts_count` holds rejected attempts on '
        'the same row.',
        '',
        f'- Verified submissions: **{report["accuracy"]["verified"]}**',
        f'- Rejected attempts: **{report["accuracy"]["failed"]}**',
        f'- Overall accuracy: **{report["accuracy"]["overall"]}%**',
        '',
        '### By conversion type',
        '',
        _table(
            ['Conversion type', 'Entries', 'Verified', 'Failed', 'Accuracy'],
            [[row['type'], row['entries'], row['verified'], row['failed'],
              f'{row["accuracy"]}%' if row['accuracy'] is not None else '—']
             for row in report['accuracy']['by_type']],
        ),
        '',
        '### By module phase',
        '',
        _table(
            ['Phase', 'Entries', 'Verified', 'Failed', 'Accuracy'],
            [[row['phase'], row['entries'], row['verified'], row['failed'],
              f'{row["accuracy"]}%' if row['accuracy'] is not None else '—']
             for row in report['accuracy']['by_phase']],
        ),
        '',
        '### By sub-step',
        '',
        _table(
            ['Sub-step', 'Entries', 'Verified', 'Failed', 'Accuracy'],
            [[row['sub_step'], row['entries'], row['verified'], row['failed'],
              f'{row["accuracy"]}%' if row['accuracy'] is not None else '—']
             for row in report['accuracy']['by_substep']],
        ),
        '',
        '## 9. XP and progression',
        '',
        f'- Total XP awarded: **{report["xp"]["total"]}**',
        f'- Mean XP per account: **{report["xp"]["mean"] if report["xp"]["mean"] is not None else "—"}** · '
        f'median: **{report["xp"]["median"] if report["xp"]["median"] is not None else "—"}** · '
        f'max: **{report["xp"]["max"] if report["xp"]["max"] is not None else "—"}**',
        f'- Accounts with XP: **{report["xp"]["earned_accounts"]}** of '
        f'**{engagement["accounts"]}**',
        '',
        _table(
            ['Level', 'Accounts'],
            [[row['level'], row['accounts']] for row in report['xp']['levels']],
        ),
        '',
        f'Levels advance every {XP_PER_LEVEL} XP.',
        '',
        '## 10. Activity timeline (ISO weeks)',
        '',
        _table(
            ['ISO year', 'ISO week', 'Telemetry events'],
            [[row['iso_year'], row['iso_week'], row['events']]
             for row in report['timeline']],
        ),
        '',
        '## 11. Data quality notes',
        '',
        '- This report is descriptive. It does not establish learning gains or causal effects.',
        '- Accounts with no telemetry, progress, lane history, or synthesis attempts are '
        'counted as registered but inactive.',
        '- Telemetry pseudo-labels (`checkpoint`, `balance`, `molar_mass`, `comparison`, '
        '`deduction`) record module-level events and are intentionally not matched to a '
        '`ProblemPart` row.',
        '- Generated `SYN_*` problems are excluded from catalog, completion, and accuracy '
        'figures; they exist only for the Synthesis Challenge.',
        '- Stage flags are cumulative: a learner who clears a later gate normally still '
        'holds the earlier flags.',
    ]

    outliers = report['diagnostics']['answer_outliers']
    if outliers:
        lines += [
            '',
            '### Answer recomputation outliers',
            '',
            _table(
                ['Problem', 'Part', 'Recomputed', 'Stored', 'Delta'],
                [[row['problem_id'], row['part_label'], row['recomputed'],
                  row['stored'], row['delta']] for row in outliers],
            ),
            '',
            f'These differences are at most '
            f'{report["diagnostics"]["answer_outlier_max_pct"]:.2f}% of the stored '
            'answer and come from rounding when the seed data was authored. Grading '
            'compares fraction nodes, not the stored answer, so the differences do '
            'not change pass/fail outcomes; they only affect the displayed worked '
            'answer.',
        ]

    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = (
        'Print a read-only Results and Validation report for the configured '
        'database (markdown or json).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--format',
            choices=['markdown', 'json', 'both'],
            default='markdown',
            help='Output format. Default: markdown.',
        )
        parser.add_argument(
            '--output',
            help=(
                'Write to this path instead of stdout. For --format both, the '
                'extension is added automatically (.md and .json).'
            ),
        )

    def handle(self, *args, **options):
        report = _collect(timezone.now())
        output_format = options['format']
        output_path = options['output']

        markdown = _render_markdown(report)
        payload = json.dumps(report, indent=2, default=str)

        if output_format == 'json':
            if output_path:
                self._write(Path(output_path), payload)
                self.stdout.write(self.style.SUCCESS(f'Wrote {output_path}'))
            else:
                self.stdout.write(payload)
            return

        if output_format == 'markdown':
            if output_path:
                self._write(Path(output_path), markdown)
                self.stdout.write(self.style.SUCCESS(f'Wrote {output_path}'))
            else:
                self.stdout.write(markdown)
            return

        if not output_path:
            raise CommandError('--format both requires --output.')

        base = Path(output_path)
        markdown_path = base.with_suffix('.md')
        json_path = base.with_suffix('.json')
        self._write(markdown_path, markdown)
        self._write(json_path, payload)
        self.stdout.write(self.style.SUCCESS(
            f'Wrote {markdown_path} and {json_path}'))

    def _write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(content)
