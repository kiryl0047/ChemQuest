import json
import random
import re
from datetime import timedelta
from itertools import permutations

from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.http import HttpResponse, JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import (
    StoichiometryProblem, ProblemPart, StudentTelemetryLog,
    Substance, UserProfile, ProblemProgress, PartProgress, SynthesisAttempt,
    XP_PER_NODE_CORRECT, XP_PER_PART_COMPLETE,
    XP_PER_BALANCE, XP_PER_LIMITING_TRACK, XP_PER_DEDUCTION,
)

# ===========================================================================
# Tunable assessment-policy constants
# ===========================================================================
M1_ACCURACY_THRESHOLD       = 80.0   # documented Module 1 accuracy gate (%)
SYNTHESIS_ELIGIBILITY_COUNT = 5      # completed problems to unlock review
SYNTHESIS_PASS_PCT          = 60.0
SYNTHESIS_ITEM_COUNT        = 3
NODE_TOLERANCE              = 0.01
LANE_TOLERANCE              = 0.05
YIELD_TOLERANCE             = 0.2
EXCESS_TOLERANCE            = 0.25

DIATOMIC_FORMULAS = {'H2', 'O2', 'N2', 'Cl2', 'F2', 'Br2', 'I2'}

CONVERSION_TYPE_LABELS = ['mol_to_mol', 'mol_to_g', 'g_to_mol', 'g_to_g']


# ===========================================================================
# Context Processor — injects XP/level into every template automatically
# ===========================================================================

def global_user_status(request):
    if request.user.is_authenticated:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        return {
            'user_level':            profile.level,
            'user_total_xp':         profile.total_xp,
            'user_xp_into_level':    profile.xp_into_current_level,
            'user_level_progress_pct': profile.level_progress_pct,
        }
    return {
        'user_level':              1,
        'user_total_xp':           0,
        'user_xp_into_level':      0,
        'user_level_progress_pct': 0,
    }


# ===========================================================================
# Auth views
# ===========================================================================

def student_login(request):
    if request.user.is_authenticated:
        return redirect('problem_lobby')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            UserProfile.objects.get_or_create(user=user)
            return redirect('problem_lobby')
    else:
        form = AuthenticationForm()

    return render(request, 'login.html', {'form': form})


def student_logout(request):
    logout(request)
    return redirect('student_login')


def register(request):
    if request.user.is_authenticated:
        return redirect('problem_lobby')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('problem_lobby')
    else:
        form = UserCreationForm()

    return render(request, 'register.html', {'form': form})


# ===========================================================================
# Internal helpers
# ===========================================================================

def _all_problems():
    return StoichiometryProblem.objects.prefetch_related('parts').order_by('problem_id')


def _get_problem_or_first(prob_id):
    try:
        return StoichiometryProblem.objects.get(problem_id=prob_id)
    except StoichiometryProblem.DoesNotExist:
        return StoichiometryProblem.objects.order_by('problem_id').first()


def _get_coeff(problem, formula):
    for entry in problem.reactants + problem.products:
        if entry['formula'] == formula:
            return entry['coeff']
    raise ValueError(f"Formula '{formula}' not found in problem {problem.problem_id}")


def _unique_formulas(problem):
    all_formulas = [r['formula'] for r in problem.reactants] + \
                   [p['formula'] for p in problem.products]
    return list(dict.fromkeys(all_formulas))


def _parse_substance_atoms(formula):
    atoms = {}
    for elem, count in re.findall(r'([A-Z][a-z]*)(\d*)', formula):
        atoms[elem] = atoms.get(elem, 0) + (int(count) if count else 1)
    return atoms


def _mass_tolerance(formula):
    """Tolerance scales with formula complexity instead of a flat ±0.5."""
    total_atoms = sum(_parse_substance_atoms(formula).values()) or 1
    return min(1.0, 0.10 + 0.05 * total_atoms)


def _award_xp(request, xp_amount: int):
    if xp_amount > 0 and request.user.is_authenticated:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.total_xp += xp_amount
        profile.save()


def _log_attempt(request, prob_id, part_label, sub_step, module_phase, is_correct):
    """
    Per-user telemetry row. Attempts_count increments only on failures,
    mirroring the original convention.
    """
    defaults = {'attempts_count': 0}
    kwargs = dict(
        problem_id=prob_id,
        part_label=part_label,
        sub_step=sub_step,
        module_phase=module_phase,
    )
    if request.user.is_authenticated:
        kwargs['user'] = request.user
    else:
        kwargs['user'] = None
    log, _ = StudentTelemetryLog.objects.get_or_create(**kwargs, defaults=defaults)
    if not is_correct:
        log.attempts_count += 1
    log.is_correct = is_correct
    log.save()
    return log


def _backfill_progress_from_telemetry(progress):
    """One-time adoption shim: derive 1A/1B clears from pre-existing telemetry."""
    if progress.balancing_cleared and progress.molar_mass_cleared:
        return
    qs = StudentTelemetryLog.objects.filter(
        user=progress.user, problem_id=progress.problem_id, module_phase=1,
    )
    if not progress.balancing_cleared and \
            qs.filter(sub_step='1A', is_correct=True).exists():
        progress.balancing_cleared = True
    if not progress.molar_mass_cleared and \
            qs.filter(sub_step='1B', is_correct=True).exists():
        progress.molar_mass_cleared = True
    progress.save()


def _part_context(part: ProblemPart):
    """Units-only node specs. Expected numeric values never leave the server."""
    nodes = part.expected_node_units()
    gf = part.given_substance.formula
    tf = part.target_substance.formula
    gq = float(part.given_quantity)
    gu = part.given_unit
    tu = part.target_unit

    return {
        'conversion_type': part.conversion_type,
        'node_count':      part.node_count,
        'nodes_json':      json.dumps(nodes),
        'given_formula':   gf,
        'given_quantity':  gq,
        'given_unit':      gu,
        'target_formula':  tf,
        'target_unit':     tu,
        'starting_label':  f"{gq} {'g' if gu == 'g' else 'mol'} {gf}",
        'target_label':    f"? {'g' if tu == 'g' else 'mol'} {tf}",
        'part_label':      part.part_label,
        'part_prompt':     part.part_prompt,
    }


def _navigation_context(problem: StoichiometryProblem, current_part: ProblemPart):
    all_parts = list(problem.parts.all())
    idx = next((i for i, p in enumerate(all_parts) if p.pk == current_part.pk), 0)

    prev_part = all_parts[idx - 1] if idx > 0 else None
    next_part = all_parts[idx + 1] if idx < len(all_parts) - 1 else None
    is_last_part = next_part is None
    goes_to_module3 = is_last_part and problem.is_limiting_problem

    return {
        'all_parts':        all_parts,
        'current_part_idx': idx,
        'prev_part':        prev_part,
        'next_part':        next_part,
        'is_last_part':     is_last_part,
        'goes_to_module3':  goes_to_module3,
    }


def _completed_problems_count(user):
    problems = {p.problem_id: p for p in StoichiometryProblem.objects.all()}
    completed = 0
    for prog in ProblemProgress.objects.filter(user=user):
        problem = problems.get(prog.problem_id)
        if problem and prog.is_completed(problem):
            completed += 1
    return completed


# ---------------------------------------------------------------------------
# Module 2 chain-grading engine (flexible chemically-valid orderings)
# ---------------------------------------------------------------------------

def _unit_signature(nodes):
    return [(str(n.get('num_unit') or ''), str(n.get('den_unit') or '')) for n in nodes]


def _prefix_matches(chain, prefix):
    """True when a candidate chain begins with exactly the verified prefix
    (units equal and values within tolerance at every position)."""
    try:
        for c_node, p_node in zip(chain, prefix):
            if c_node['num_unit'] != p_node['num_unit'] or \
               c_node['den_unit'] != p_node['den_unit']:
                return False
            if abs(float(p_node['num_value']) - float(c_node['num_value'])) >= NODE_TOLERANCE:
                return False
            if abs(float(p_node['den_value']) - float(c_node['den_value'])) >= NODE_TOLERANCE:
                return False
        return True
    except (TypeError, ValueError):
        return False


def _valid_chains(part):
    """All permutations of the expected nodes that keep dimensional validity:
    each denominator must cancel the previous numerator, starting at the
    given unit and ending at the target unit."""
    expected = part.expected_nodes()
    start_unit = f"{part.given_unit}_{part.given_substance.formula}"
    end_unit = f"{part.target_unit}_{part.target_substance.formula}"

    valid = []
    for perm in permutations(expected):
        prev = start_unit
        ok = True
        for n in perm:
            if n['den_unit'] != prev:
                ok = False
                break
            prev = n['num_unit']
        if ok and prev == end_unit:
            valid.append(list(perm))
    return valid or [list(expected)]


def _grade_chain(part, submitted_nodes):
    """
    Returns dict:
      count_ok   — submitted node count matches requirement
      matched    — units align with a dimensionally-valid chain
      reports    — per-index {index, unit_ok, value_ok}
      all_ok     — every node fully correct
    """
    node_count = part.node_count
    if len(submitted_nodes) != node_count:
        return {'count_ok': False, 'matched': False, 'expected': None,
                'reports': [], 'all_ok': False}

    chains = _valid_chains(part)
    sig = _unit_signature(submitted_nodes)
    matched = next((c for c in chains if _unit_signature(c) == sig), None)

    if matched is None:
        start_unit = f"{part.given_unit}_{part.given_substance.formula}"
        known_nums = {n['num_unit'] for n in part.expected_nodes()}
        prev = start_unit
        reports = []
        for i, (num_u, den_u) in enumerate(sig):
            unit_ok = (den_u == prev) and (num_u in known_nums)
            reports.append({'index': i, 'unit_ok': unit_ok, 'value_ok': None})
            if den_u == prev:
                prev = num_u
        return {'count_ok': True, 'matched': False, 'expected': None,
                'reports': reports, 'all_ok': False}

    reports = []
    all_ok = True
    for i, (sub, exp) in enumerate(zip(submitted_nodes, matched)):
        try:
            num_val = float(sub.get('num_value'))
            den_val = float(sub.get('den_value'))
            value_ok = (
                abs(num_val - exp['num_value']) < NODE_TOLERANCE and
                abs(den_val - exp['den_value']) < NODE_TOLERANCE
            )
        except (TypeError, ValueError):
            value_ok = False
        all_ok = all_ok and value_ok
        reports.append({'index': i, 'unit_ok': True, 'value_ok': value_ok})

    return {'count_ok': True, 'matched': True, 'expected': matched,
            'reports': reports, 'all_ok': all_ok}


# ---------------------------------------------------------------------------
# Module 3 limiting-reagent analysis (explicit, not inferred)
# ---------------------------------------------------------------------------

def _compute_limiting_analysis(problem):
    """
    Explicit derivation: each lane converts its given reactant fully into the
    primary product; the smallest primary-product yield identifies the true
    limiting reagent. Excess leftovers follow from the limiting extent.
    """
    parts = list(problem.parts.all().order_by('order'))
    primary_product = problem.products[0]['formula'] if problem.products else ''

    tracks = []
    for p in parts:
        tracks.append({
            'part_label':     p.part_label,
            'given_formula':  p.given_substance.formula,
            'target_formula': p.target_substance.formula,
            'yield_value':    float(p.correct_answer),
            'targets_primary': p.target_substance.formula == primary_product,
        })

    primary_tracks = [t for t in tracks if t['targets_primary']]
    limiting_track = min(primary_tracks, key=lambda t: t['yield_value']) \
        if primary_tracks else None

    excess_expected = {}
    if limiting_track:
        lim_part = next(p for p in parts
                        if p.part_label == limiting_track['part_label'])
        lim_coeff = _get_coeff(problem, lim_part.given_substance.formula)
        prod_coeff = _get_coeff(problem, primary_product)

        mm_lim = float(lim_part.given_substance.molar_mass)
        moles_lim = (float(lim_part.given_quantity) / mm_lim
                     if lim_part.given_unit == 'g'
                     else float(lim_part.given_quantity))
        moles_product = moles_lim * prod_coeff / lim_coeff

        for t in tracks:
            if t is limiting_track or not t['targets_primary']:
                continue
            exc_part = next(p for p in parts if p.part_label == t['part_label'])
            exc_coeff = _get_coeff(problem, exc_part.given_substance.formula)
            mm_exc = float(exc_part.given_substance.molar_mass)
            moles_exc_start = (float(exc_part.given_quantity) / mm_exc
                               if exc_part.given_unit == 'g'
                               else float(exc_part.given_quantity))
            moles_used = moles_product * exc_coeff / prod_coeff
            moles_left = moles_exc_start - moles_used
            excess_expected[t['given_formula']] = round(moles_left * mm_exc, 4)

    return {
        'primary_product': primary_product,
        'tracks':          tracks,
        'limiting_track':  limiting_track,
        'excess_expected': excess_expected,
    }


# ---------------------------------------------------------------------------
# Module 1 scaffold / guide checkpoints
#
# These gates verify UNDERSTANDING rather than a preferred balancing order.
# Balancing is trial-and-error: a student may legally begin on any element
# and still reach a correct result. The questions below therefore have a
# single correct answer independent of ordering strategy, and frame
# balancing around conservation of mass.
#
#   kind='entry'  -> asked before balancing begins (conceptual gate)
#   kind='exit'   -> asked before leaving Module 1 for Module 2
#                    (replaces the removed retention/retrieval gate)
# ---------------------------------------------------------------------------
_ENTRY_CHECKPOINT = {
    'question': ('In balancing, why is it correct to change only the '
                 'coefficients in front of formulas, and never the '
                 'subscripts inside a formula?'),
    'options': [
        'Coefficients scale the whole compound while preserving its identity',
        'Subscripts are easier to rewrite than coefficients',
        'Coefficients are the only numbers provided in the problem',
        'Changing subscripts makes the numbers on each side match more easily',
    ],
    'accept': [
        'Coefficients scale the whole compound while preserving its identity',
    ],
}

_EXIT_CHECKPOINT = {
    'question': ('After a reaction is balanced, which statement must be '
                 'true for every element on both sides of the arrow?'),
    'options': [
        'The number of atoms of each element is equal on both sides',
        'The two sides contain the same total number of compounds',
        'Each compound shares at least one element with the other side',
        'The heaviest element is listed first on each side',
    ],
    'accept': [
        'The number of atoms of each element is equal on both sides',
    ],
}


def _build_checkpoint_question(problem, kind='entry'):
    return {
        'kind': 'entry' if kind == 'entry' else 'exit',
        'question': _ENTRY_CHECKPOINT['question'] if kind == 'entry'
                    else _EXIT_CHECKPOINT['question'],
        'options': _ENTRY_CHECKPOINT['options'] if kind == 'entry'
                   else _EXIT_CHECKPOINT['options'],
        'accept': _ENTRY_CHECKPOINT['accept'] if kind == 'entry'
                  else _EXIT_CHECKPOINT['accept'],
    }


# ---------------------------------------------------------------------------
# Shared molar-mass breakdown hint
# ---------------------------------------------------------------------------

def _molar_mass_breakdown_hints(formulas, problem=None, entered_map=None):
    hints = []
    for formula in formulas:
        try:
            entered = float((entered_map or {}).get(formula))
        except (TypeError, ValueError):
            entered = None

        coeff = None
        if problem:
            for entry in problem.reactants + problem.products:
                if entry['formula'] == formula:
                    coeff = entry['coeff']
                    break
        if entered is not None and coeff and coeff > 1:
            expected_row = Substance.objects.filter(formula=formula).first()
            if (expected_row and
                    abs(entered - expected_row.molar_mass * coeff) <= _mass_tolerance(formula)):
                hints.append(
                    f"\u26a0\ufe0f For {formula}: you multiplied by the balancing "
                    f"coefficient ({coeff}). Molar mass measures 1 mole of the "
                    f"formula alone \u2014 expected {expected_row.molar_mass:.3f} g/mol.")
                continue

        atoms = _parse_substance_atoms(formula)
        breakdown_parts = []
        for el, cnt in atoms.items():
            try:
                el_mass = Substance.objects.get(formula=el).molar_mass
                breakdown_parts.append(f"{cnt}\u00d7{el} ({el_mass:.3f})")
            except Substance.DoesNotExist:
                breakdown_parts.append(f"{cnt}\u00d7{el}")
        calc_str = " + ".join(breakdown_parts)
        hints.append(f"For {formula}: Sum {calc_str} using atomic masses "
                     f"from the databank.")
    return hints

# ===========================================================================
# View: Problem selection lobby
# ===========================================================================

@login_required
def problem_lobby(request):
    problems = _all_problems()

    answered_problem_ids = set(
        StudentTelemetryLog.objects.filter(user=request.user)
        .values_list('problem_id', flat=True)
    )
    progress_map = {
        pp.problem_id: pp
        for pp in ProblemProgress.objects.filter(user=request.user)
    }

    for problem in problems:
        problem.has_telemetry = problem.problem_id in answered_problem_ids
        prog = progress_map.get(problem.problem_id)
        problem.completed = bool(prog and prog.is_completed(problem))

    completed_count = _completed_problems_count(request.user)
    latest_synthesis = SynthesisAttempt.objects.filter(
        user=request.user).order_by('-created_at').first()
    synthesis_unlocked = completed_count >= SYNTHESIS_ELIGIBILITY_COUNT

    return render(request, 'problem_lobby.html', {
        'problems':               problems,
        'synthesis_unlocked':     synthesis_unlocked,
        'synthesis_completed':    completed_count,
        'synthesis_required':     SYNTHESIS_ELIGIBILITY_COUNT,
        'synthesis_passed':       bool(latest_synthesis and latest_synthesis.passed),
        'synthesis_best_pct':     round(latest_synthesis.score_pct, 1) if latest_synthesis else None,
    })


@login_required
def reset_problem_telemetry(request, prob_id):
    if request.user and request.user.is_authenticated:
        StudentTelemetryLog.objects.filter(
            user=request.user, problem_id=prob_id).delete()
        ProblemProgress.objects.filter(
            user=request.user, problem_id=prob_id).delete()
        PartProgress.objects.filter(
            user=request.user, problem_id=prob_id).delete()
    else:
        StudentTelemetryLog.objects.filter(
            problem_id=prob_id, user__isnull=True).delete()
        ProblemProgress.objects.filter(problem_id=prob_id, user__isnull=True).delete()
        PartProgress.objects.filter(problem_id=prob_id, user__isnull=True).delete()

    return redirect('problem_lobby')


# ===========================================================================
# View: Module 1 — Preparation Ledger
# ===========================================================================

@login_required
def preparation_ledger(request, prob_id=None):
    if prob_id:
        problem = _get_problem_or_first(prob_id)
    else:
        problem = StoichiometryProblem.objects.order_by('problem_id').first()

    if not problem:
        return render(request, 'no_problems.html')

    progress = ProblemProgress.get_or_default(request.user, problem.problem_id)
    if progress:
        _backfill_progress_from_telemetry(progress)

    first_part = problem.parts.first()
    first_label = first_part.part_label if first_part else 'a'

    verified_masses = {}
    verified_coeffs = {}
    if progress:
        if progress.balancing_cleared:
            for entry in problem.reactants + problem.products:
                verified_coeffs[entry['formula']] = entry['coeff']
        if progress.molar_mass_cleared:
            for s in Substance.objects.filter(formula__in=_unique_formulas(problem)):
                verified_masses[s.formula] = round(s.molar_mass, 4)

    entry_checkpoint = _build_checkpoint_question(problem, 'entry')
    exit_checkpoint = _build_checkpoint_question(problem, 'exit')

    context = {
        'problem_id':           problem.problem_id,
        'problem_title':        problem.title,
        'prompt':               problem.prompt,
        'reactants':            problem.reactants,
        'products':             problem.products,
        'target_substances':    _unique_formulas(problem),
        'first_part_label':     first_label,
        'next_url':             f"/workspace/{problem.problem_id}/{first_label}/",
        'is_limiting_problem':  problem.is_limiting_problem,
        'all_problems':         list(_all_problems()),
        'progress_json': json.dumps({
            'balancingCleared':      progress.balancing_cleared if progress else False,
            'molarMassCleared':      progress.molar_mass_cleared if progress else False,
            'checkpointCleared':     progress.checkpoint_cleared if progress else False,
            'exitCheckpointCleared': progress.exit_checkpoint_cleared if progress else False,
            'verifiedMasses':        verified_masses,
            'verifiedCoeffs':        verified_coeffs,
        }),
        'checkpoint_json': json.dumps({
            'entry': {
                'question': entry_checkpoint['question'],
                'options':  entry_checkpoint['options'],
            },
            'exit': {
                'question': exit_checkpoint['question'],
                'options':  exit_checkpoint['options'],
            },
        }),
    }
    return render(request, 'module1_ledger.html', context)


# ===========================================================================
# View: Module 2 — Step-Grid Workspace
# ===========================================================================

@login_required
def step_grid_workspace(request, prob_id, part_label='a'):
    problem = _get_problem_or_first(prob_id)
    if not problem:
        return render(request, 'no_problems.html')

    progress = ProblemProgress.get_or_default(request.user, problem.problem_id)
    if not progress or not progress.module1_complete():
        return redirect('preparation_ledger', prob_id=problem.problem_id)

    part = get_object_or_404(ProblemPart, problem=problem, part_label=part_label)
    nav_ctx = _navigation_context(problem, part)
    part_progress = PartProgress.get_or_default(
        request.user, problem.problem_id, part.part_label)

    verified_answer = (
        f"{float(part.correct_answer):.4f} {part.target_unit} "
        f"{part.target_substance.formula}"
        if part_progress.lane_cleared else None
    )

    context = {
        'problem_id':    problem.problem_id,
        'problem_title': problem.title,
        'prompt':        problem.prompt,
        **_part_context(part),
        **nav_ctx,
        'verified_chain_json': json.dumps(part_progress.chain_json or []),
        'verified_prefix_json': json.dumps(part_progress.verified_prefix_json or []),
        'lane_cleared': part_progress.lane_cleared,
        'verified_answer': verified_answer,
    }
    return render(request, 'module2_workspace.html', context)


# ===========================================================================
# View: Module 3 — Limiting Reagent Workspace
# ===========================================================================

@login_required
@csrf_exempt
def limiting_workspace(request, prob_id):
    problem = _get_problem_or_first(prob_id)
    if not problem:
        return render(request, 'no_problems.html')

    progress = ProblemProgress.get_or_default(request.user, problem.problem_id)
    if not progress or not progress.module1_complete():
        return redirect('preparation_ledger', prob_id=problem.problem_id)

    parts_queryset = problem.parts.all().order_by('order')
    if not parts_queryset.exists():
        return render(request, 'no_problems.html')

    analysis = _compute_limiting_analysis(problem)

    part_progress_map = {
        pp.part_label: pp
        for pp in PartProgress.objects.filter(
            user=request.user, problem_id=problem.problem_id)
    }

    # =======================================================================
    # HANDLE ASYNC POST AUDITS
    # =======================================================================
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid JSON format.'})

        action = data.get('action')

        if action == 'verify_lane':
            part_label = data.get('part_label')
            if not part_label:
                return JsonResponse({'success': False, 'message': 'Missing target part label.'})

            try:
                current_part = parts_queryset.get(part_label__iexact=part_label)
            except ProblemPart.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Part tracking mismatch configuration.'})

            expected_nodes = current_part.expected_nodes()
            submitted_nodes = data.get('nodes', [])

            if len(submitted_nodes) != len(expected_nodes):
                return JsonResponse({'success': False, 'message': 'Please fill out all fractional nodes.'})

            error_index = None
            for i, expected in enumerate(expected_nodes):
                try:
                    sub_num = float(submitted_nodes[i].get('num_value'))
                    sub_den = float(submitted_nodes[i].get('den_value'))
                except (TypeError, ValueError):
                    error_index = i
                    break
                if (abs(sub_num - expected['num_value']) > LANE_TOLERANCE or
                        abs(sub_den - expected['den_value']) > LANE_TOLERANCE):
                    error_index = i
                    break

            if error_index is not None:
                log = _log_attempt(request, problem.problem_id,
                                   current_part.part_label, 'lane', 3, False)
                return JsonResponse({
                    'success': False,
                    'attempts': log.attempts_count,
                    'hint': _lane_hint(log.attempts_count,
                                       expected_nodes[error_index]),
                    'message': f'Calculation variance discovered in step box {error_index + 1}. Check conversion constants.',
                    'error_node_index': error_index,
                })

            _log_attempt(request, problem.problem_id,
                         current_part.part_label, 'lane', 3, True)

            pp = PartProgress.get_or_default(
                request.user, problem.problem_id, current_part.part_label)
            first_clear = not pp.lane_cleared
            pp.lane_cleared = True
            pp.chain_json = [
                {'num_value': float(n.get('num_value')),
                 'num_unit':  n.get('num_unit'),
                 'den_value': float(n.get('den_value')),
                 'den_unit':  n.get('den_unit')}
                for n in submitted_nodes
            ]
            pp.save()

            if first_clear:
                _award_xp(request, XP_PER_LIMITING_TRACK)

            correct_answer_val = float(current_part.correct_answer)
            target_formula = current_part.target_substance.formula
            return JsonResponse({
                'success': True,
                'is_correct': True,
                'message': f'Part {part_label.upper()} confirmed and logged securely!',
                'correct_answer': f'{correct_answer_val:.4f} g {target_formula}',
                'answer_label': f'COMPUTED YIELD — PART {part_label.upper()}',
            })

        elif action == 'verify_comparison':
            if not analysis['limiting_track']:
                return JsonResponse({'success': False, 'message': 'No comparable tracks configured.'})

            cleared_labels = [lbl for lbl, pp in part_progress_map.items() if pp.lane_cleared]
            all_cleared = all(
                part_progress_map.get(p.part_label) and part_progress_map[p.part_label].lane_cleared
                for p in parts_queryset
            )
            if not all_cleared:
                return JsonResponse({'success': False, 'message': 'Verify every conversion lane first.'})

            choice = data.get('choice_track')
            is_correct = (choice == analysis['limiting_track']['part_label'])
            log = _log_attempt(request, problem.problem_id, 'comparison', '3C', 3, is_correct)

            if is_correct:
                progress.yield_comparison_verified = True
                progress.save()
                yield_lines = [
                    f"Track {t['part_label'].upper()} ({t['given_formula']}): "
                    f"{t['yield_value']:.4f} g {analysis['primary_product']}"
                    for t in analysis['tracks'] if t['targets_primary']
                ]
                return JsonResponse({
                    'success': True,
                    'attempts': log.attempts_count,
                    'message': 'Yield comparison confirmed. Proceed to final deduction.',
                    'yield_summary': yield_lines,
                })

            hint = ''
            if log.attempts_count >= 2:
                hint = ('Compare the computed yields side by side — the smaller '
                        'product amount came from the reactant that runs out first.')
            return JsonResponse({
                'success': False,
                'attempts': log.attempts_count,
                'hint': hint,
                'message': 'That track does not produce the smaller yield.',
            })

        elif action == 'verify_deduction':
            if not progress.yield_comparison_verified:
                return JsonResponse({
                    'success': False,
                    'message': 'Complete the side-by-side yield comparison first.'
                })

            limiting_reagent   = data.get('limiting_reagent')
            theoretical_yield  = data.get('theoretical_yield')
            excess_remaining   = data.get('excess_remaining', {}) or {}

            lim = analysis['limiting_track']
            if not lim:
                return JsonResponse({'success': False, 'message': 'Limiting analysis unavailable for this problem.'})

            true_limiting_formula = lim['given_formula']
            lowest_yield = lim['yield_value']

            try:
                submitted_yield = float(theoretical_yield)
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'message': 'Numerical value required for theoretical yield.'})

            excess_errors = []
            for formula, expected_left in analysis['excess_expected'].items():
                try:
                    val = float(excess_remaining.get(formula))
                except (TypeError, ValueError):
                    excess_errors.append(formula)
                    continue
                if abs(val - expected_left) > max(EXCESS_TOLERANCE, 0.02 * expected_left):
                    excess_errors.append(formula)

            limiting_match = (limiting_reagent == true_limiting_formula)
            yield_match = abs(submitted_yield - lowest_yield) < YIELD_TOLERANCE
            excess_ok = not excess_errors

            is_correct = limiting_match and yield_match and excess_ok
            log = _log_attempt(request, problem.problem_id, 'deduction', '3D', 3, is_correct)

            if is_correct:
                progress.deduction_cleared = True
                progress.limiting_reagent = limiting_reagent or ''
                progress.theoretical_yield = str(theoretical_yield) if theoretical_yield not in (None, '') else ''
                try:
                    progress.excess_remaining_json = json.dumps(excess_remaining)
                except (TypeError, ValueError):
                    progress.excess_remaining_json = ''
                progress.save()
                _award_xp(request, XP_PER_DEDUCTION)
                return JsonResponse({
                    'success': True,
                    'attempts': log.attempts_count,
                    'message': 'Chemical synthesis sequence master cleared! Redirecting...',
                    'next_url': '/problem_lobby/',
                })

            hint = _deduction_hint(
                log.attempts_count,
                limiting_match, yield_match, excess_ok,
                true_limiting_formula, analysis,
            )

            if not limiting_match:
                message = 'Incorrect Limiting Reagent assignment.'
            elif not yield_match:
                message = 'Theoretical product yield mass calculation error.'
            else:
                message = (f'Excess-reagent remaining incorrect for: '
                           f'{", ".join(excess_errors)}.')
            return JsonResponse({
                'success': False,
                'attempts': log.attempts_count,
                'hint': hint,
                'message': message,
                'excess_errors': excess_errors,
            })

        return JsonResponse({'success': False, 'message': 'Unknown execution parameter.'})

    # =======================================================================
    # HANDLE GET PAGE RENDERING
    # =======================================================================
    all_lanes_cleared = all(
        part_progress_map.get(p.part_label) and part_progress_map[p.part_label].lane_cleared
        for p in parts_queryset
    )
    if not all_lanes_cleared:
        first_uncleared = next(
            (p.part_label for p in parts_queryset
             if not (part_progress_map.get(p.part_label) and part_progress_map[p.part_label].lane_cleared)),
            None
        )
        if first_uncleared:
            return redirect('step_grid_workspace',
                            prob_id=problem.problem_id,
                            part_label=first_uncleared)

    processed_parts = []
    for idx, p in enumerate(parts_queryset):
        pp = part_progress_map.get(p.part_label)
        processed_parts.append({
            'part_label':      p.part_label,
            'part_prompt':     p.part_prompt,
            'given_quantity':  float(p.given_quantity),
            'given_unit':      p.given_unit,
            'given_formula':   p.given_substance.formula,
            'target_formula':  p.target_substance.formula,
            'node_units':      p.expected_node_units(),
            'chain_json':      json.dumps(pp.chain_json or []) if pp else '[]',
            'cleared':         bool(pp and pp.lane_cleared),
            'index':           idx,
        })

    cleared_tracks = [t for t in analysis['tracks']]
    excess_formulas = list(analysis['excess_expected'].keys())

    context = {
        'problem':          problem,
        'problem_id':       problem.problem_id,
        'problem_title':    problem.title,
        'prompt':           problem.prompt,
        'processed_parts':  processed_parts,
        'reactants':        problem.reactants,
        'target_formula':   analysis['primary_product'],
        'tracks_json':      json.dumps([
            {'part_label': t['part_label'], 'given_formula': t['given_formula']}
            for t in cleared_tracks if t['targets_primary']
        ]),
        'excess_formulas_json': json.dumps(excess_formulas),
        'comparison_verified':  progress.yield_comparison_verified,
        'deduction_cleared':    progress.deduction_cleared,
        'deduction_limiting':   progress.limiting_reagent,
        'deduction_yield':      progress.theoretical_yield,
        'deduction_excess':     progress.excess_remaining_json or '{}',
    }
    return render(request, 'module3_limiting.html', context)


def _lane_hint(attempts, expected_node):
    if attempts == 1:
        return (f"This step converts from '{expected_node['den_unit']}' to "
                f"'{expected_node['num_unit']}'. The value you entered does not "
                f"match — recheck which constant belongs in this slot.")
    return (f"Node units: numerator '{expected_node['num_unit']}' over "
            f"denominator '{expected_node['den_unit']}' should be "
            f"num {expected_node['num_value']} over den {expected_node['den_value']}. "
            f"Recompute the conversion constant and its placement.")


def _deduction_hint(attempts, limiting_match, yield_match, excess_ok,
                    true_limiting, analysis):
    if attempts == 1:
        if not limiting_match:
            return ("Directional nudge: look at your two verified lanes — "
                    "which reactant's line produced LESS product?")
        if not yield_match:
            return ("The theoretical yield equals the SMALLER of your two "
                    "computed product amounts.")
        return ("Excess remaining = starting grams minus grams consumed. "
                "Consumed follows the mole ratio from the limiting extent.")
    if attempts == 2:
        if not limiting_match:
            return ("Rule reminder: the reactant yielding the SMALLEST "
                    "product amount is the limiting reagent.")
        if not yield_match:
            return ("Copy the smaller verified lane yield exactly — it IS "
                    "the theoretical yield.")
        return ("For each excess reactant: convert limiting moles to product "
                "moles, then back to excess-reactant grams consumed, and "
                "subtract from what you started with.")
    return (f"Strongest hint: {true_limiting} is the limiting reagent; its "
            f"lane yield is the theoretical yield. Excess left = start \u2212 consumed.")


# ===========================================================================
# Module 4: Student-Facing Telemetry Analytics & Performance Dashboard
# ===========================================================================

def _dashboard_context(user):
    logs = StudentTelemetryLog.objects.filter(user=user)
    total_attempts = logs.aggregate(total=Sum('attempts_count'))['total'] or 0
    total_verified = logs.filter(is_correct=True).count()

    accuracy = 0
    if total_attempts + total_verified > 0:
        accuracy = round((total_verified / (total_attempts + total_verified)) * 100, 1)

    concept_metrics = {}
    for c_type in CONVERSION_TYPE_LABELS:
        matching_parts = ProblemPart.objects.filter(conversion_type=c_type)
        part_labels = list(matching_parts.values_list('part_label', flat=True))
        prob_ids = list(matching_parts.values_list('problem__problem_id', flat=True))

        type_logs = logs.filter(problem_id__in=prob_ids, part_label__in=part_labels)
        failures = type_logs.aggregate(total=Sum('attempts_count'))['total'] or 0
        successes = type_logs.filter(is_correct=True).count()

        concept_metrics[c_type] = {
            'label': c_type.replace('_', ' ').upper(),
            'failures': failures,
            'successes': successes,
            'score': round((successes / (failures + successes)) * 100, 1)
            if (failures + successes) > 0 else None,
        }

    weakest_concept = None
    lowest_score = 101
    for c_type, data in concept_metrics.items():
        if data['score'] is not None and data['score'] < lowest_score:
            lowest_score = data['score']
            weakest_concept = data['label']

    trouble_ids = logs.filter(attempts_count__gte=2).values_list(
        'problem_id', flat=True).distinct()
    recommended_problems = list(
        StoichiometryProblem.objects.filter(problem_id__in=trouble_ids)[:3])

    if not recommended_problems:
        attempted_ids = logs.values_list('problem_id', flat=True).distinct()
        recommended_problems = list(
            StoichiometryProblem.objects.exclude(problem_id__in=attempted_ids)[:3])

    trend_series = _trend_series(logs)
    depth_metrics, position_metrics = _skill_depth_metrics(logs)

    latest_synthesis = SynthesisAttempt.objects.filter(
        user=user).order_by('-created_at').first()
    completed_count = _completed_problems_count(user)
    synthesis_unlocked = completed_count >= SYNTHESIS_ELIGIBILITY_COUNT

    return {
        'total_attempts': total_attempts,
        'total_verified': total_verified,
        'accuracy': accuracy,
        'concept_metrics': concept_metrics,
        'weakest_concept': weakest_concept or 'None (All Clear!)',
        'recommended_problems': recommended_problems,
        'has_history': total_attempts > 0 or total_verified > 0,
        'trend_series': trend_series,
        'depth_metrics': depth_metrics,
        'position_metrics': position_metrics,
        'synthesis_unlocked': synthesis_unlocked,
        'synthesis_completed': completed_count,
        'synthesis_required': SYNTHESIS_ELIGIBILITY_COUNT,
        'synthesis_passed': bool(latest_synthesis and latest_synthesis.passed),
        'synthesis_best_pct': round(latest_synthesis.score_pct, 1) if latest_synthesis else None,
    }


def _trend_series(logs, days=14):
    """Accuracy-over-time per conversion type from created_at timestamps."""
    start_date = timezone.now().date() - timedelta(days=days - 1)
    recent = logs.filter(created_at__date__gte=start_date).exclude(user=None)

    part_type_map = {
        (pp.problem.problem_id, pp.part_label): pp.conversion_type
        for pp in ProblemPart.objects.select_related('problem')
    }

    buckets = {}
    for lg in recent:
        ctype = part_type_map.get((lg.problem_id, lg.part_label))
        if not ctype:
            continue
        day = timezone.localtime(lg.created_at).date() if timezone.get_current_timezone() else lg.created_at.date()
        key = (day, ctype)
        cell = buckets.setdefault(key, [0, 0])
        cell[0] += 1 if lg.is_correct else 0
        cell[1] += lg.attempts_count + (1 if lg.is_correct else 0)

    dates = [start_date + timedelta(days=i) for i in range(days)]
    series = []
    for ctype in CONVERSION_TYPE_LABELS:
        points = []
        for d in dates:
            succ, tries = buckets.get((d, ctype), (0, 0))
            points.append({
                'date': d.strftime('%m-%d'),
                'score': round(succ / tries * 100, 1) if tries > 0 else None,
            })

        coords = []
        n = len(points)
        for i, pt in enumerate(points):
            if pt['score'] is None:
                continue
            x = 10 + (i / max(n - 1, 1)) * 300
            y = 65 - (pt['score'] / 100) * 55
            coords.append(f"{x:.1f},{y:.1f}")

        series.append({
            'label': ctype.replace('_', ' ').upper(),
            'points': points,
            'polyline': ' '.join(coords),
            'has_data': len(coords) >= 2,
        })
    return series


def _skill_depth_metrics(logs):
    """Finer diagnostic buckets: chain depth and within-chain failure position."""
    part_map = {
        (pp.problem.problem_id, pp.part_label): pp
        for pp in ProblemPart.objects.all()
    }

    depth = {
        'single_node': {'label': 'Single-node chains (mol\u2192mol)', 'successes': 0, 'tries': 0},
        'multi_node':  {'label': 'Multi-node chains (2\u20133 steps)', 'successes': 0, 'tries': 0},
    }
    positions = {
        'first':  {'label': 'First node of chain', 'successes': 0, 'tries': 0},
        'middle': {'label': 'Middle node of chain', 'successes': 0, 'tries': 0},
        'last':   {'label': 'Final node of chain', 'successes': 0, 'tries': 0},
    }

    for lg in logs.filter(module_phase=2):
        pp = part_map.get((lg.problem_id, lg.part_label))
        if not pp:
            continue
        tries = lg.attempts_count + (1 if lg.is_correct else 0)
        succ = 1 if lg.is_correct else 0

        bucket = 'single_node' if pp.node_count == 1 else 'multi_node'
        depth[bucket]['successes'] += succ
        depth[bucket]['tries'] += tries

        if str(lg.sub_step).isdigit():
            i = int(lg.sub_step)
            n = max(pp.node_count, 1)
            hit_positions = []
            if i == 0:
                hit_positions.append('first')
                if n == 1:
                    hit_positions.append('last')
            elif i == n - 1:
                hit_positions.append('last')
            else:
                hit_positions.append('middle')
            for pos in hit_positions:
                positions[pos]['successes'] += succ
                positions[pos]['tries'] += tries

    for store in (depth, positions):
        for item in store.values():
            item['score'] = round(item['successes'] / item['tries'] * 100, 1) \
                if item['tries'] > 0 else None

    ordered_positions = [positions['first'], positions['middle'], positions['last']]
    return list(depth.values()), ordered_positions


@login_required
def student_dashboard(request):
    context = _dashboard_context(request.user)
    return render(request, 'module4_dashboard.html', context)


@login_required
def dashboard_export_pdf(request):
    from io import BytesIO
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    ctx = _dashboard_context(request.user)
    if not ctx['has_history']:
        return redirect(f"{reverse('student_dashboard')}?export=empty")

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 1.0 * inch

    def line(text, size=11, bold=False, dy=18, color=(0.1, 0.1, 0.15)):
        nonlocal y
        pdf.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
        pdf.setFillColorRGB(*color)
        pdf.drawString(1.0 * inch, y, text)
        y -= dy

    line('ChemQuest Performance Report', 20, bold=True, dy=24)
    line(f'Student: {request.user.username}', 12, dy=16)
    line(f'Generated: {timezone.localtime().strftime("%Y-%m-%d %H:%M")}', 10, dy=28)

    line('Summary Metrics', 14, bold=True, dy=22)
    line(f'Total verified solves: {ctx["total_verified"]}')
    line(f'Total retry attempts: {ctx["total_attempts"]}')
    line(f'Overall accuracy: {ctx["accuracy"]}%')
    line(f'Weakest concept: {ctx["weakest_concept"]}')
    y -= 8

    line('Conversion-Type Mastery', 14, bold=True, dy=22)
    for data in ctx['concept_metrics'].values():
        score_txt = f'{data["score"]}%' if data['score'] is not None else 'No data'
        line(f'  {data["label"]}: {score_txt}  '
             f'({data["successes"]} clear / {data["failures"]} missed)')
    y -= 8

    line('Skill Depth Breakdown', 14, bold=True, dy=22)
    for item in ctx['depth_metrics']:
        score_txt = f'{item["score"]}%' if item['score'] is not None else 'No data'
        line(f'  {item["label"]}: {score_txt}')
    for item in ctx['position_metrics']:
        if item['tries'] > 0:
            line(f'  {item["label"]}: {item["score"]}%')
    y -= 8

    line('Synthesis Challenge', 14, bold=True, dy=22)
    line(f'Review unlocked: {"Yes" if ctx["synthesis_unlocked"] else "No"}'
         f'  ({ctx["synthesis_completed"]}/{ctx["synthesis_required"]} problems complete)')
    if ctx['synthesis_best_pct'] is not None:
        line(f'Best unassisted-review score: {ctx["synthesis_best_pct"]}%'
             f'  ({"PASSED" if ctx["synthesis_passed"] else "not yet passed"})')

    line('Recommended Targets', 14, bold=True, dy=22)
    if ctx['recommended_problems']:
        for problem in ctx['recommended_problems']:
            line(f'  [{problem.problem_id}] {problem.title}')
    else:
        line('  All current pipelines operating at maximum efficiency.')

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="chemquest_report_{request.user.username}.pdf"'
    )
    return response


# ===========================================================================
# Instructor-only analytics (strict separation via Django is_staff)
# ===========================================================================

def _cohort_analytics():
    users = User.objects.filter(is_staff=False).order_by('username')
    roster = []

    for u in users:
        logs = StudentTelemetryLog.objects.filter(user=u)
        total_tries = logs.aggregate(t=Sum('attempts_count'))['t'] or 0
        verified = logs.filter(is_correct=True).count()
        tries = total_tries + verified
        accuracy = round(verified / tries * 100, 1) if tries > 0 else None

        cells = {}
        weakest = None
        lowest = 101.0
        for c_type in CONVERSION_TYPE_LABELS:
            parts = ProblemPart.objects.filter(conversion_type=c_type)
            type_logs = logs.filter(
                problem_id__in=parts.values_list('problem__problem_id', flat=True),
                part_label__in=parts.values_list('part_label', flat=True),
            )
            fails = type_logs.aggregate(t=Sum('attempts_count'))['t'] or 0
            succ = type_logs.filter(is_correct=True).count()
            score = round(succ / (fails + succ) * 100, 1) if (fails + succ) > 0 else None
            cells[c_type] = score
            if score is not None and score < lowest:
                lowest = score
                weakest = c_type

        profile = getattr(u, 'profile', None)
        roster.append({
            'username':   u.username,
            'level':      profile.level if profile else 1,
            'total_xp':   profile.total_xp if profile else 0,
            'tries':      tries,
            'verified':   verified,
            'accuracy':   accuracy,
            'cells':      cells,
            'cell_list':  [(ct, cells[ct]) for ct in CONVERSION_TYPE_LABELS],
            'weakest':    weakest,
        })

    cohort_accuracy = None
    accuracies = [r['accuracy'] for r in roster if r['accuracy'] is not None]
    if accuracies:
        cohort_accuracy = round(sum(accuracies) / len(accuracies), 1)

    needing_review = sum(
        1 for r in roster
        if r['accuracy'] is not None and r['accuracy'] < M1_ACCURACY_THRESHOLD
    )

    return roster, cohort_accuracy, needing_review


@staff_member_required
def instructor_dashboard(request):
    roster, cohort_accuracy, needing_review = _cohort_analytics()
    return render(request, 'instructor_dashboard.html', {
        'roster': roster,
        'cohort_accuracy': cohort_accuracy,
        'needing_review': needing_review,
        'conversion_types': CONVERSION_TYPE_LABELS,
    })


# ===========================================================================
# Synthesis Challenge — randomized unassisted review (Module 2 extension)
# ===========================================================================

def _synthesis_eligible_parts(user):
    problems = {p.problem_id: p for p in StoichiometryProblem.objects.prefetch_related('parts')}
    eligible = []
    for prog in ProblemProgress.objects.filter(user=user):
        problem = problems.get(prog.problem_id)
        if problem and prog.is_completed(problem):
            eligible.extend(problem.parts.all())
    return eligible


@login_required
def synthesis_challenge(request):
    eligible = _synthesis_eligible_parts(request.user)
    if len(eligible) < 1 or _completed_problems_count(request.user) < SYNTHESIS_ELIGIBILITY_COUNT:
        return redirect('problem_lobby')

    picks = random.sample(list(eligible),
                          min(SYNTHESIS_ITEM_COUNT, len(eligible)))
    items = []
    for part in picks:
        ctx = _part_context(part)
        ctx['problem_id'] = part.problem.problem_id
        ctx['problem_title'] = part.problem.title
        items.append(ctx)

    exam_items = [{
        'problem_id':   it['problem_id'],
        'part_label':   it['part_label'],
        'node_count':   it['node_count'],
        'node_units':   json.loads(it['nodes_json']),
        'given_label':  it['starting_label'],
        'target_label': it['target_label'],
        'title':        it['problem_title'],
    } for it in items]

    return render(request, 'synthesis_challenge.html', {
        'items': items,
        'exam_items_json': json.dumps(exam_items),
        'pass_threshold': SYNTHESIS_PASS_PCT,
    })


@login_required
@csrf_exempt
def synthesis_submit(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method.'})

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON.'})

    answers = data.get('answers', [])
    if not answers:
        return JsonResponse({'success': False, 'message': 'No answers submitted.'})

    results = []
    correct_items = 0
    for ans in answers:
        prob_id = ans.get('problem_id')
        part_label = ans.get('part_label')
        submitted = ans.get('nodes', [])
        try:
            part = ProblemPart.objects.get(
                problem__problem_id=prob_id, part_label=part_label)
        except ProblemPart.DoesNotExist:
            results.append({'problem_id': prob_id, 'part_label': part_label,
                            'correct': False})
            continue

        grade = _grade_chain(part, submitted)
        item_correct = grade['count_ok'] and grade['matched'] and grade['all_ok']
        correct_items += 1 if item_correct else 0

        _log_attempt(request, prob_id, part_label, 'synthesis', 5, item_correct)
        results.append({
            'problem_id': prob_id,
            'part_label': part_label,
            'correct':    item_correct,
            'reports':    grade['reports'] if not item_correct else [],
        })

    total = max(len(answers), 1)
    score_pct = round(correct_items / total * 100, 1)
    passed = score_pct >= SYNTHESIS_PASS_PCT

    SynthesisAttempt.objects.create(
        user=request.user,
        total_items=len(answers),
        correct_items=correct_items,
        score_pct=score_pct,
        passed=passed,
    )
    if passed:
        ProblemProgress.objects.filter(user=request.user).update(synthesis_passed=True)

    return JsonResponse({
        'success': True,
        'score_pct': score_pct,
        'passed': passed,
        'results': results,
        'threshold': SYNTHESIS_PASS_PCT,
    })


# ===========================================================================
# API: Award XP  (legacy client-driven endpoint; verify endpoints now
# credit XP server-side on first-time clears)
# ===========================================================================

@csrf_exempt
def award_node_xp(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': 'Login required.'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method.'}, status=405)

    try:
        data = json.loads(request.body)
        xp_amount = int(data.get('xp_amount', 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'Invalid payload.'}, status=400)

    if xp_amount <= 0:
        return JsonResponse({'success': False, 'message': 'xp_amount must be positive.'}, status=400)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.total_xp += xp_amount
    profile.save()

    return JsonResponse({
        'success':       True,
        'xp_awarded':    xp_amount,
        'total_xp':      profile.total_xp,
        'level':         profile.level,
        'xp_into_level': profile.xp_into_current_level,
        'progress_pct':  profile.level_progress_pct,
    })


# ===========================================================================
# API: Verify balancing (Sub-Step 1A)
# ===========================================================================

@csrf_exempt
def verify_balancing_backend(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'})

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON.'})

    prob_id = data.get('problem_id', '')
    submitted = data.get('coefficients', [])

    try:
        problem = StoichiometryProblem.objects.get(problem_id=prob_id)
        expected_strs = [s.strip() for s in problem.correct_coefficients.split(',') if s.strip()]
        expected_ints = [int(s) for s in expected_strs]

        try:
            submitted_ints = [int(str(s).strip()) for s in submitted]
        except (ValueError, TypeError):
            submitted_ints = []

        is_exact_match = (
            len(submitted_ints) == len(expected_ints) and
            submitted_ints == expected_ints
        )

        is_multiple_ratio = False
        scale_factor = 1
        if (not is_exact_match and len(submitted_ints) == len(expected_ints)
                and all(x > 0 for x in submitted_ints)):
            ratios = [sub / exp for sub, exp in zip(submitted_ints, expected_ints)]
            if len(set(ratios)) == 1 and ratios[0] > 1 and ratios[0].is_integer():
                is_multiple_ratio = True
                scale_factor = int(ratios[0])

        is_correct = is_exact_match

        log = _log_attempt(request, prob_id, 'balance', '1A', 1, is_correct)

        progress = ProblemProgress.get_or_default(request.user, prob_id)
        first_clear = False
        if progress and is_correct:
            first_clear = not progress.balancing_cleared
            progress.balancing_cleared = True
            progress.save()
        if first_clear:
            _award_xp(request, XP_PER_BALANCE)

        hint = ""
        if is_correct:
            message = 'Chamber Stabilized! Reaction is perfectly balanced in the simplest whole-number ratio.'
        elif is_multiple_ratio:
            message = f'Atom balance achieved, but stoichiometry requires the SIMPLEST whole-number integer ratio!'
            hint = (f"All your coefficients ({', '.join(map(str, submitted_ints))}) share a common "
                    f"divisor of {scale_factor}. Divide each coefficient by {scale_factor} to find "
                    f"the simplest whole-number ratio.")
        else:
            reactants = problem.reactants
            products = problem.products
            left_atoms = {}
            right_atoms = {}

            if len(submitted_ints) == len(reactants) + len(products):
                for i, r in enumerate(reactants):
                    c = submitted_ints[i]
                    for el, cnt in _parse_substance_atoms(r['formula']).items():
                        left_atoms[el] = left_atoms.get(el, 0) + c * cnt
                for j, p in enumerate(products):
                    c = submitted_ints[len(reactants) + j]
                    for el, cnt in _parse_substance_atoms(p['formula']).items():
                        right_atoms[el] = right_atoms.get(el, 0) + c * cnt

                mismatches = []
                all_elements = sorted(set(list(left_atoms.keys()) + list(right_atoms.keys())))
                for el in all_elements:
                    l_count = left_atoms.get(el, 0)
                    r_count = right_atoms.get(el, 0)
                    if l_count != r_count:
                        mismatches.append((el, l_count, r_count))

                if mismatches:
                    err_summaries = [f"{el}: Left has {l}, Right has {r}" for el, l, r in mismatches]
                    message = f"Reaction Imbalance! {'; '.join(err_summaries[:2])}."

                    first_el, l_c, r_c = mismatches[0]
                    if log.attempts_count == 1:
                        if l_c > r_c:
                            hint = (f"Try increasing the coefficient of the product containing {first_el} "
                                    f"to supply more {first_el} atoms on the right side.")
                        else:
                            hint = (f"Try increasing the coefficient of the reactant containing {first_el} "
                                    f"to supply more {first_el} atoms on the left side.")
                    else:
                        hint = ("Check the odd/even atom parity: If an element appears with an odd subscript "
                                "in a product but as a diatomic reactant (like O2), try doubling the odd "
                                "compound's coefficient to make it even.")
                else:
                    message = 'Reaction Imbalance Detected! Enter positive integers for all reactants and products.'
                    hint = 'Fill in all coefficient boxes with positive whole numbers (1, 2, 3...).'
            else:
                message = 'Please provide coefficients for all reactants and products.'
                hint = 'Enter an integer coefficient in every box.'

        return JsonResponse({
            'success':   is_correct,
            'attempts':  log.attempts_count,
            'xp_reward': XP_PER_BALANCE if first_clear else 0,
            'message':   message,
            'hint':      hint,
        })

    except StoichiometryProblem.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Problem not found.'})


# ===========================================================================
# API: Verify molar masses  (Sub-Step 1B)
# ===========================================================================

@csrf_exempt
def verify_molar_mass_backend(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'})

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON.'})

    prob_id = data.get('problem_id', '')
    submitted_map = data.get('molar_masses', {})

    if not prob_id or not submitted_map:
        return JsonResponse({'success': False, 'message': 'Missing problem_id or molar_masses.'})

    try:
        problem = StoichiometryProblem.objects.get(problem_id=prob_id)
    except StoichiometryProblem.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Problem not found.'})

    results = {}
    all_ok = True

    for formula, submitted_val in submitted_map.items():
        try:
            entered = float(submitted_val)
        except (TypeError, ValueError):
            results[formula] = {'correct': False, 'expected': None, 'tolerance': None}
            all_ok = False
            continue

        try:
            substance = Substance.objects.get(formula=formula)
            expected = substance.molar_mass
        except Substance.DoesNotExist:
            results[formula] = {'correct': False, 'expected': None, 'tolerance': None}
            all_ok = False
            continue

        tolerance = _mass_tolerance(formula)
        is_match = abs(entered - expected) <= tolerance
        results[formula] = {
            'correct':  is_match,
            'expected': round(expected, 3),
            'tolerance': round(tolerance, 2),
        }
        if not is_match:
            all_ok = False

    log = _log_attempt(request, prob_id, 'molar_mass', '1B', 1, all_ok)

    progress = ProblemProgress.get_or_default(request.user, prob_id)
    first_clear = False
    if progress and all_ok:
        first_clear = not progress.molar_mass_cleared
        progress.molar_mass_cleared = True
        progress.save()
    if first_clear:
        _award_xp(request, XP_PER_BALANCE)

    molar_mass_hints = []
    if not all_ok:
        wrong = [f for f, res in results.items() if not res['correct']]
        molar_mass_hints = _molar_mass_breakdown_hints(
            wrong[:2], problem=problem, entered_map=submitted_map)

    hint = " ".join(molar_mass_hints) if molar_mass_hints else ""

    return JsonResponse({
        'success':   all_ok,
        'results':   results,
        'xp_reward': XP_PER_BALANCE if first_clear else 0,
        'message': (
            'Molecular constants verified! All molar masses locked.'
            if all_ok else
            'Molar mass mismatch detected — check highlighted compounds.'
        ),
        'hint':      hint,
    })


# ===========================================================================
# API: Module 1 predict-before-calculate checkpoint
# ===========================================================================

@csrf_exempt
def m1_checkpoint(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method.'})

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON.'})

    prob_id = data.get('problem_id', '')
    choice = str(data.get('choice', '')).strip()
    kind = str(data.get('kind', 'entry')).strip()

    try:
        problem = StoichiometryProblem.objects.get(problem_id=prob_id)
    except StoichiometryProblem.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Problem not found.'})

    question = _build_checkpoint_question(problem, kind)
    is_correct = choice in question['accept']

    sub_step = '1P' if kind == 'entry' else '1Q'
    log = _log_attempt(request, prob_id, 'checkpoint', sub_step, 1, is_correct)

    progress = ProblemProgress.get_or_default(request.user, prob_id)
    if progress and is_correct:
        if kind == 'entry':
            progress.checkpoint_cleared = True
        else:
            progress.exit_checkpoint_cleared = True
        progress.save()

    if is_correct:
        message = ('Good — you reasoned about what balancing preserves. '
                   'Coefficient inputs unlocked.'
                   if kind == 'entry' else
                   'Module 1 confirmed — you are ready for the solving workspace.')
    else:
        message = ('Not quite — think about what balancing must preserve '
                   'between the two sides.'
                   if kind == 'entry' else
                   'Not quite — reconsider what a balanced reaction guarantees.')

    return JsonResponse({
        'success': is_correct,
        'attempts': log.attempts_count,
        'kind': question['kind'],
        'message': message,
         'hint': (question['question']
                 if not is_correct and log.attempts_count >= 2 else ''),
    })


# ===========================================================================
# API: Audit a full Module 2 conversion chain
# ===========================================================================

@csrf_exempt
def audit_chain(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method.'})

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON.'})

    prob_id = data.get('problem_id')
    part_label = data.get('part_label', 'a')
    submitted = data.get('nodes', [])

    try:
        problem = StoichiometryProblem.objects.get(problem_id=prob_id)
        part = ProblemPart.objects.get(problem=problem, part_label=part_label)
    except (StoichiometryProblem.DoesNotExist, ProblemPart.DoesNotExist):
        return JsonResponse({'success': False, 'message': 'Problem or part not found.'})

    progress = ProblemProgress.get_or_default(request.user, prob_id)
    if not progress or not progress.module1_complete():
        return JsonResponse({'success': False, 'message': 'Module 1 gate not satisfied.'}, status=403)

    part_progress = PartProgress.get_or_default(request.user, prob_id, part_label)

    if part_progress.lane_cleared:
        return JsonResponse({'success': True, 'already_cleared': True, 'all_ok': True})

    parsed_nodes = []
    for raw in submitted:
        parsed_nodes.append({
            'num_value': raw.get('num_value'),
            'num_unit':  str(raw.get('num_unit') or '').strip(),
            'den_value': raw.get('den_value'),
            'den_unit':  str(raw.get('den_unit') or '').strip(),
        })

    grade = _grade_chain(part, parsed_nodes)

    if not grade['count_ok']:
        return JsonResponse({
            'success': False,
            'message': f'This conversion requires exactly {part.node_count} step factor(s).',
            'reports': [],
        })

    xp_reward = 0
    if grade['matched'] and grade['all_ok']:
        first_clear = not part_progress.lane_cleared
        part_progress.lane_cleared = True
        part_progress.chain_json = [
            {'num_value': float(n['num_value']), 'num_unit': n['num_unit'],
             'den_value': float(n['den_value']), 'den_unit': n['den_unit']}
            for n in parsed_nodes
        ]
        part_progress.save()

        for i in range(part.node_count):
            _log_attempt(request, prob_id, part_label, str(i), 2, True)

        if first_clear:
            xp_reward = XP_PER_NODE_CORRECT * part.node_count + XP_PER_PART_COMPLETE
            _award_xp(request, xp_reward)

        return JsonResponse({
            'success': True,
            'all_ok': True,
            'reports': grade['reports'],
            'xp_reward': xp_reward,
            'correct_answer': f"{float(part.correct_answer):.4f} {part.target_unit} {part.target_substance.formula}",
            'message': 'Conversion chain verified — all units cancelled cleanly!',
        })

    for i, rep in enumerate(grade['reports']):
        node_ok = bool(rep['unit_ok'] and rep['value_ok'])
        _log_attempt(request, prob_id, part_label, str(i), 2, node_ok)

    start_unit = f"{part.given_unit}_{part.given_substance.formula}"
    prev = start_unit
    messages = []
    for rep in grade['reports']:
        idx = rep['index'] + 1
        if not rep['unit_ok']:
            num_unit = str(parsed_nodes[rep['index']].get('num_unit') or '')
            den_unit = str(parsed_nodes[rep['index']].get('den_unit') or '')
            need = prev.replace('_', ' ')
            entered = den_unit.replace('_', ' ') if den_unit else '(empty)'
            if num_unit == prev:
                messages.append(
                    f'Step {idx}: the denominator must cancel "{need}" '
                    f'(the unit the previous step ended in), but you wrote '
                    f'"{entered}".')
            else:
                messages.append(
                    f'Step {idx}: this factor should convert "{need}" forward, '
                    f'but your units ({entered}) do not continue from it.')
        elif rep['value_ok'] is False:
            exp = grade['expected'][rep['index']]
            messages.append(
                f'Step {idx}: units are correct but the VALUES are off — for '
                f'this constant use num {exp["num_value"]} over den {exp["den_value"]}.')
        if rep['unit_ok']:
            prev = str(parsed_nodes[rep['index']].get('num_unit') or '')
    return JsonResponse({
        'success': False,
        'matched_units': grade['matched'],
        'reports': grade['reports'],
        'message': ' '.join(messages) or 'Chain verification failed.',
    })


# ===========================================================================
# API: Verify a single Module 2 node (progressive step-by-step flow)
# ===========================================================================

@csrf_exempt
def verify_node(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method.'})

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON.'})

    prob_id = data.get('problem_id')
    part_label = data.get('part_label', 'a')
    raw_node = data.get('node')

    if not isinstance(raw_node, dict):
        return JsonResponse({'success': False, 'message': 'Missing node payload.'})

    current = {
        'num_value': raw_node.get('num_value'),
        'num_unit':  str(raw_node.get('num_unit') or '').strip(),
        'den_value': raw_node.get('den_value'),
        'den_unit':  str(raw_node.get('den_unit') or '').strip(),
    }

    try:
        problem = StoichiometryProblem.objects.get(problem_id=prob_id)
        part = ProblemPart.objects.get(problem=problem, part_label=part_label)
    except (StoichiometryProblem.DoesNotExist, ProblemPart.DoesNotExist):
        return JsonResponse({'success': False, 'message': 'Problem or part not found.'})

    progress = ProblemProgress.get_or_default(request.user, prob_id)
    if not progress or not progress.module1_complete():
        return JsonResponse({'success': False, 'message': 'Module 1 gate not satisfied.'}, status=403)

    part_progress = PartProgress.get_or_default(request.user, prob_id, part_label)

    if part_progress.lane_cleared:
        return JsonResponse({'success': True, 'already_cleared': True, 'complete': True})

    prefix = part_progress.verified_prefix_json or []
    index = len(prefix)

    if index >= part.node_count:
        return JsonResponse({'success': False, 'message': 'All steps already verified.'})

    candidates = [c for c in _valid_chains(part) if _prefix_matches(c, prefix)]

    unit_ok = any(
        c[index]['num_unit'] == current['num_unit'] and
        c[index]['den_unit'] == current['den_unit']
        for c in candidates
    )

    correct = False
    matched_chain = None
    if unit_ok:
        try:
            num_val = float(current['num_value'])
            den_val = float(current['den_value'])
        except (TypeError, ValueError):
            num_val = den_val = None

        for c in candidates:
            exp = c[index]
            if num_val is None:
                break
            if abs(num_val - float(exp['num_value'])) < NODE_TOLERANCE and \
               abs(den_val - float(exp['den_value'])) < NODE_TOLERANCE:
                correct = True
                matched_chain = c
                break

    _log_attempt(request, prob_id, part_label, str(index), 2, correct)

    if not correct:
        prev_unit = (f"{part.given_unit}_{part.given_substance.formula}"
                     if index == 0 else prefix[-1]['num_unit'])
        if not unit_ok:
            need = prev_unit.replace('_', ' ')
            entered_num = str(current['num_unit'] or '').replace('_', ' ')
            entered_den = str(current['den_unit'] or '').replace('_', ' ')
            message = (f'Step {index + 1}: this factor must cancel "{need}" '
                       f'(the unit the previous step ended in), but you wrote '
                       f'"{entered_num} over {entered_den}".')
        else:
            expected_value = None
            for c in candidates:
                if _prefix_matches(c, prefix) and c[index]['num_unit'] == current['num_unit'] \
                        and c[index]['den_unit'] == current['den_unit']:
                    expected_value = c[index]
                    break
            if expected_value:
                message = (f'Step {index + 1}: units are correct but the VALUES '
                           f'are off — for this constant use num '
                           f'{expected_value["num_value"]} over den '
                           f'{expected_value["den_value"]}.')
            else:
                message = (f'Step {index + 1}: units are correct but the VALUES '
                           f'are off — recheck your arithmetic for that constant.')

        return JsonResponse({
            'success': False,
            'unit_ok': unit_ok,
            'message': message,
        })

    verified_entry = {
        'num_value': float(matched_chain[index]['num_value']),
        'num_unit':  current['num_unit'],
        'den_value': float(matched_chain[index]['den_value']),
        'den_unit':  current['den_unit'],
    }

    if index + 1 == part.node_count:
        first_clear = not part_progress.lane_cleared
        part_progress.lane_cleared = True
        part_progress.chain_json = prefix + [verified_entry]
        part_progress.save()

        if first_clear:
            xp_reward = XP_PER_NODE_CORRECT * part.node_count + XP_PER_PART_COMPLETE
            _award_xp(request, xp_reward)
        else:
            xp_reward = 0

        return JsonResponse({
            'success': True,
            'correct': True,
            'complete': True,
            'xp_reward': xp_reward,
            'correct_answer': f"{float(part.correct_answer):.4f} {part.target_unit} {part.target_substance.formula}",
            'message': 'Conversion chain verified — all units cancelled cleanly!',
        })

    part_progress.verified_prefix_json = prefix + [verified_entry]
    part_progress.save()

    return JsonResponse({
        'success': True,
        'correct': True,
        'complete': False,
        'verified_count': index + 1,
        'message': f'Step {index + 1} verified.',
    })


# ===========================================================================
# API: Locked constants for the canned-constants tray (server-fed)
# ===========================================================================

@login_required
def api_locked_constants(request, prob_id):
    prog = ProblemProgress.objects.filter(
        user=request.user, problem_id=prob_id, molar_mass_cleared=True,
    ).first()
    if not prog:
        return JsonResponse({'locked': False, 'molarMasses': {}, 'coefficients': {}})

    problem = get_object_or_404(StoichiometryProblem, problem_id=prob_id)
    formulas = _unique_formulas(problem)
    masses = {
        s.formula: round(s.molar_mass, 4)
        for s in Substance.objects.filter(formula__in=formulas)
    }
    coefficients = {
        entry['formula']: entry['coeff']
        for entry in problem.reactants + problem.products
    }
    return JsonResponse({
        'locked': True,
        'molarMasses': masses,
        'coefficients': coefficients,
    })
