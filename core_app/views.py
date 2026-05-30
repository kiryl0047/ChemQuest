import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db.models import Sum, Avg, Count, Q

from .models import (
    StoichiometryProblem, ProblemPart, StudentTelemetryLog,
    UserProfile, NODE_COUNT,
    XP_PER_NODE_CORRECT, XP_PER_PART_COMPLETE,
    XP_PER_BALANCE, XP_PER_LIMITING_TRACK, XP_PER_DEDUCTION,
)


# ===========================================================================
# Context Processor — injects XP/level into every template automatically
# ===========================================================================

def global_user_status(request):
    """
    Registered in settings.py TEMPLATES context_processors.
    Provides user level and XP data to every template without
    requiring each view to pass them manually.
    """
    if request.user.is_authenticated:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        return {
            'user_level':            profile.level,
            'user_total_xp':         profile.total_xp,
            'user_xp_into_level':    profile.xp_into_current_level,
            'user_level_progress_pct': profile.level_progress_pct,
        }
    # Anonymous fallback — safe zero values
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
            # Ensure a profile exists for this user
            UserProfile.objects.get_or_create(user=user)
            return redirect('problem_lobby')
    else:
        form = AuthenticationForm()

    return render(request, 'login.html', {'form': form})


def student_logout(request):
    logout(request)
    return redirect('student_login')


# ===========================================================================
# Internal helpers
# ===========================================================================

def _all_problems():
    """Return all problems with their parts pre-fetched, ordered by problem_id."""
    return StoichiometryProblem.objects.prefetch_related('parts').order_by('problem_id')


def _get_problem_or_first(prob_id):
    try:
        return StoichiometryProblem.objects.get(problem_id=prob_id)
    except StoichiometryProblem.DoesNotExist:
        return StoichiometryProblem.objects.order_by('problem_id').first()


def _part_context(part: ProblemPart):
    """Build the template context dict that drives node rendering for one ProblemPart."""
    nodes = part.expected_nodes()
    gf    = part.given_substance.formula
    tf    = part.target_substance.formula
    gq    = float(part.given_quantity)
    gu    = part.given_unit
    tu    = part.target_unit

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
        'correct_answer':  float(part.correct_answer),
        'part_label':      part.part_label,
        'part_prompt':     part.part_prompt,
    }


def _navigation_context(problem: StoichiometryProblem, current_part: ProblemPart):
    """
    Returns navigation context for Module 2.
    For limiting problems the last lane part routes to Module 3
    instead of the lobby.
    """
    all_parts = list(problem.parts.all())
    idx       = next((i for i, p in enumerate(all_parts) if p.pk == current_part.pk), 0)

    prev_part    = all_parts[idx - 1] if idx > 0 else None
    next_part    = all_parts[idx + 1] if idx < len(all_parts) - 1 else None
    is_last_part = next_part is None

    # For limiting problems: last lane part → Module 3
    goes_to_module3 = is_last_part and problem.is_limiting_problem

    return {
        'all_parts':        all_parts,
        'current_part_idx': idx,
        'prev_part':        prev_part,
        'next_part':        next_part,
        'is_last_part':     is_last_part,
        'goes_to_module3':  goes_to_module3,
    }


def _award_xp(request, xp_amount: int):
    """Award XP to the logged-in user's profile. No-op for anonymous users."""
    if request.user.is_authenticated:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.total_xp += xp_amount
        profile.save()


# ===========================================================================
# View: Problem selection lobby
# ===========================================================================

@login_required
def problem_lobby(request):
    """
    Renders the central hub of problem selections.
    Identifies which problems have been answered/attempted to conditionally
    toggle the Reset option.
    """
    problems = _all_problems()
    
    # Gather a unique list of problem IDs that this user has telemetry data for
    answered_problem_ids = set(
        StudentTelemetryLog.objects.filter(user=request.user)
        .values_list('problem_id', flat=True)
    )

    # Attach a dynamic check property onto each problem object
    for problem in problems:
        problem.has_telemetry = problem.problem_id in answered_problem_ids

    return render(request, 'problem_lobby.html', {
        'problems': problems
    })

@login_required
def reset_problem_telemetry(request, prob_id):
    """
    Deletes telemetry log historical data for a given problem ID
    so the student can loop back and re-attempt execution nodes.
    """
    if request.user and request.user.is_authenticated:
        # 1. Clear database rows for logged-in accounts
        StudentTelemetryLog.objects.filter(
            user=request.user,
            problem_id=prob_id
        ).delete()
    else:
        # 2. Clear database rows where user might be assigned as null/anonymous
        StudentTelemetryLog.objects.filter(
            problem_id=prob_id,
            user__isnull=True
        ).delete()
        
    # Redirect directly back to the problem selection screen (Lobby)
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

    reactants       = problem.reactants
    products        = problem.products
    all_formulas    = [r['formula'] for r in reactants] + [p['formula'] for p in products]
    unique_formulas = list(dict.fromkeys(all_formulas))

    first_part  = problem.parts.first()
    first_label = first_part.part_label if first_part else 'a'

    # All problems always start at Module 2 (even limiting ones)
    next_url = f'/workspace/{problem.problem_id}/{first_label}/'

    context = {
        'problem_id':           problem.problem_id,
        'problem_title':        problem.title,
        'prompt':               problem.prompt,
        'reactants':            reactants,
        'products':             products,
        'target_substances':    unique_formulas,
        'correct_coefficients': problem.correct_coefficients,
        'first_part_label':     first_label,
        'next_url':             next_url,
        'is_limiting_problem':  problem.is_limiting_problem,
        'all_problems':         list(_all_problems()),
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

    part    = get_object_or_404(ProblemPart, problem=problem, part_label=part_label)
    nav_ctx = _navigation_context(problem, part)

    context = {
        'problem_id':    problem.problem_id,
        'problem_title': problem.title,
        'prompt':        problem.prompt,
        **_part_context(part),
        **nav_ctx,
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

    from .models import Substance, _get_coeff
    import json

    parts_queryset = problem.parts.all().order_by('order')
    if not parts_queryset.exists():
        return render(request, 'no_problems.html')

    # Ensure we know the target formula from the first manufacturing line
    first_product_frm = problem.products[0]['formula'] if problem.products else ''

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
                # Use __iexact to safely pull the part whether it comes in as 'a' or 'A'
                current_part = parts_queryset.get(part_label__iexact=part_label)
            except ProblemPart.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Part tracking mismatch configuration.'})

            expected_nodes = current_part.expected_nodes()
            submitted_nodes = data.get('nodes', [])

            if len(submitted_nodes) != len(expected_nodes):
                return JsonResponse({'success': False, 'message': 'Please fill out all fractional nodes.'})

            TOLERANCE = 0.05
            for i, expected in enumerate(expected_nodes):
                try:
                    sub_num = float(submitted_nodes[i].get('num_value'))
                    sub_den = float(submitted_nodes[i].get('den_value'))
                except (TypeError, ValueError):
                    return JsonResponse({
                        'success': False,
                        'message': f'Empty or invalid value inside node step {i+1}.',
                        'error_node_index': i
                    })

                if abs(sub_num - expected['num_value']) > TOLERANCE or abs(sub_den - expected['den_value']) > TOLERANCE:
                    return JsonResponse({
                        'success': False,
                        'message': f'Calculation variance discovered in step box {i+1}. Check conversion constants.',
                        'error_node_index': i
                    })
            correct_answer_val = float(current_part.correct_answer)
            target_formula = current_part.target_substance.formula
            return JsonResponse({
                'success': True,
                'is_correct': True,
                'message': f'Part {part_label.upper()} confirmed and logged securely!',
                'correct_answer': f'{correct_answer_val:.4f} g {target_formula}',
                'answer_label': f'COMPUTED YIELD — PART {part_label.upper()}'
            })
        elif action == 'verify_deduction':
            limiting_reagent = data.get('limiting_reagent')
            theoretical_yield = data.get('theoretical_yield')

            # Look up correct answer by finding the lowest yield among manufacturing lines
            true_limiting_formula = None
            lowest_yield = float('inf')

            for p in parts_queryset:
                if p.target_substance.formula == first_product_frm:
                    ans = float(p.correct_answer)
                    if ans < lowest_yield:
                        lowest_yield = ans
                        true_limiting_formula = p.given_substance.formula

            try:
                submitted_yield = float(theoretical_yield)
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'message': 'Numerical value required for theoretical yield.'})

            limiting_match = (limiting_reagent == true_limiting_formula)
            yield_match = abs(submitted_yield - lowest_yield) < 0.2

            if limiting_match and yield_match:
                return JsonResponse({
                    'success': True,
                    'message': 'Chemical synthesis sequence master cleared! Redirecting...',
                    'next_url': '/problem_lobby/'
                })
            else:
                if not limiting_match:
                    return JsonResponse({'success': False, 'message': 'Incorrect Limiting Reagent assignment.'})
                return JsonResponse({'success': False, 'message': 'Theoretical product yield mass calculation error.'})

        return JsonResponse({'success': False, 'message': 'Unknown execution parameter.'})

    # =======================================================================
    # HANDLE GET PAGE RENDERING
    # =======================================================================
    processed_parts = []
    for idx, p in enumerate(parts_queryset):
        processed_parts.append({
            'part_label':      p.part_label,
            'part_prompt':     p.part_prompt,
            'given_quantity':  float(p.given_quantity),
            'given_unit':      p.given_unit,
            'given_formula':   p.given_substance.formula,
            'target_formula':  p.target_substance.formula,
            'nodes':           p.expected_nodes(), # Full sequence array populated here
            'index':           idx
        })

    context = {
        'problem':          problem,
        'problem_id':       problem.problem_id,
        'problem_title':    problem.title,
        'prompt':           problem.prompt,
        'processed_parts':  processed_parts,
        'reactants':        problem.reactants,
        'target_formula':   first_product_frm,
    }
    return render(request, 'module3_limiting.html', context)

# ===========================================================================
# Module 4: Student-Facing Telemetry Analytics & Performance Dashboard
# ===========================================================================

@login_required
def student_dashboard(request):
    # Fetch all logs for calculations
    logs = StudentTelemetryLog.objects.all()
    total_attempts = logs.aggregate(total=Sum('attempts_count'))['total'] or 0
    total_verified = logs.filter(is_correct=True).count()
    
    # Calculate general master accuracy
    accuracy = 0
    if total_attempts + total_verified > 0:
        accuracy = round((total_verified / (total_attempts + total_verified)) * 100, 1)

    # Conceptual Diagnostic: Map failure rates by Conversion Type
    conversion_types = ['mol_to_mol', 'mol_to_g', 'g_to_mol', 'g_to_g']
    concept_metrics = {}
    
    for c_type in conversion_types:
        # Find all parts corresponding to this conversion strategy flag
        matching_parts = ProblemPart.objects.filter(conversion_type=c_type)
        part_labels = matching_parts.values_list('part_label', flat=True)
        prob_ids = matching_parts.values_list('problem__problem_id', flat=True)
        
        # Aggregate logs matching these parts
        type_logs = logs.filter(problem_id__in=prob_ids, part_label__in=part_labels)
        failures = type_logs.aggregate(total=Sum('attempts_count'))['total'] or 0
        successes = type_logs.filter(is_correct=True).count()
        
        concept_metrics[c_type] = {
            'label': c_type.replace('_', ' ').upper(),
            'failures': failures,
            'successes': successes,
            'score': round((successes / (failures + successes)) * 100, 1) if (failures + successes) > 0 else None
        }

    # Identify the weakest concept category based on scores
    weakest_concept = None
    lowest_score = 101
    for c_type, data in concept_metrics.items():
        if data['score'] is not None and data['score'] < lowest_score:
            lowest_score = data['score']
            weakest_concept = data['label']

    # Target Re-Entry Queue: Find problem IDs where failures are high (> 2 attempts)
    trouble_ids = logs.filter(attempts_count__gte=2).values_list('problem_id', flat=True).distinct()
    recommended_problems = StoichiometryProblem.objects.filter(problem_id__in=trouble_ids)[:3]

    # If the student is doing perfectly, suggest unattempted or master challenges
    if not recommended_problems.exists():
        attempted_ids = logs.values_list('problem_id', flat=True).distinct()
        recommended_problems = StoichiometryProblem.objects.exclude(problem_id__in=attempted_ids)[:3]

    context = {
        'total_attempts': total_attempts,
        'total_verified': total_verified,
        'accuracy': accuracy,
        'concept_metrics': concept_metrics,
        'weakest_concept': weakest_concept or 'None (All Clear!)',
        'recommended_problems': recommended_problems,
    }
    return render(request, 'module4_dashboard.html', context)

# ===========================================================================
# API: Award XP  (called from JS after each verified action)
# ===========================================================================

@csrf_exempt
def award_node_xp(request):
    """
    POST { xp_amount: int, reason: str }
    Awards XP to the authenticated user's profile and returns updated totals.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': 'Login required.'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method.'}, status=405)

    try:
        data       = json.loads(request.body)
        xp_amount  = int(data.get('xp_amount', 0))
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
# API: Verify balancing
# ===========================================================================

@csrf_exempt
def verify_balancing_backend(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'})

    try:
        data      = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON.'})

    prob_id   = data.get('problem_id', '')
    submitted = data.get('coefficients', [])

    try:
        problem  = StoichiometryProblem.objects.get(problem_id=prob_id)
        expected = problem.correct_coefficients.split(',')
        is_correct = (
            len(submitted) == len(expected) and
            all(str(s).strip() == str(e).strip() for s, e in zip(submitted, expected))
        )

        log, _ = StudentTelemetryLog.objects.get_or_create(
            problem_id=prob_id,
            part_label='balance',
            module_phase=1,
            defaults={'attempts_count': 0},
        )
        log.attempts_count += 1
        log.is_correct = is_correct
        if request.user.is_authenticated:
            log.user = request.user
        log.save()

        return JsonResponse({
            'success':  is_correct,
            'attempts': log.attempts_count,
            'xp_reward': XP_PER_BALANCE if is_correct else 0,
            'message':  (
                'Chamber Stabilized! Reaction is perfectly balanced.'
                if is_correct else
                'Reaction Imbalance Detected! Try checking atom ratios.'
            ),
        })

    except StoichiometryProblem.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Problem not found.'})


# ===========================================================================
# API: Validate a single step-node answer
# ===========================================================================

@csrf_exempt
def validate_step_node(request):
    """
    POST { problem_id, part_label, node_index, num_value, num_unit,
           den_value, den_unit, is_final_node }
    Returns { success, message, xp_reward }
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method.'})

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON.'})

    prob_id      = data.get('problem_id')
    part_label   = data.get('part_label', 'a')
    node_idx     = int(data.get('node_index', 0))
    is_final     = bool(data.get('is_final_node', False))

    try:
        problem = StoichiometryProblem.objects.get(problem_id=prob_id)
        part    = ProblemPart.objects.get(problem=problem, part_label=part_label)
    except (StoichiometryProblem.DoesNotExist, ProblemPart.DoesNotExist):
        return JsonResponse({'success': False, 'message': 'Problem or part not found.'})

    nodes = part.expected_nodes()
    if node_idx >= len(nodes):
        return JsonResponse({'success': False, 'message': 'Node index out of range.'})

    expected  = nodes[node_idx]
    TOLERANCE = 0.01

    try:
        num_val = float(data.get('num_value'))
        den_val = float(data.get('den_value'))
    except (TypeError, ValueError):
        return JsonResponse({
            'success': False,
            'message': 'Empty or invalid input — fill in both fields before submitting.',
        })

    num_ok = abs(num_val - expected['num_value']) < TOLERANCE
    den_ok = abs(den_val - expected['den_value']) < TOLERANCE
    is_correct = num_ok and den_ok

    # Telemetry
    log, _ = StudentTelemetryLog.objects.get_or_create(
        problem_id=prob_id,
        part_label=part_label,
        module_phase=2,
        defaults={'attempts_count': 0},
    )
    if not is_correct:
        log.attempts_count += 1
    log.is_correct = is_correct
    if request.user.is_authenticated:
        log.user = request.user
    log.save()

    # XP: base per correct node + bonus if this completes the part
    xp_reward = 0
    if is_correct:
        xp_reward = XP_PER_NODE_CORRECT
        if is_final:
            xp_reward += XP_PER_PART_COMPLETE

    return JsonResponse({
        'success':    is_correct,
        'xp_reward':  xp_reward,
        'message': (
            f'Node {node_idx + 1} verified! Units cancel correctly.'
            if is_correct else
            'Incorrect — check values and unit labels.'
        ),
    })