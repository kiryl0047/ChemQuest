import json
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum, Avg, Count, Q

from .models import (
    StoichiometryProblem, ProblemPart, StudentTelemetryLog,
    NODE_COUNT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_problems():
    """Return all problems with their first part pre-fetched, ordered by id."""
    return StoichiometryProblem.objects.prefetch_related('parts').order_by('problem_id')


def _get_problem_or_first(prob_id):
    try:
        return StoichiometryProblem.objects.get(problem_id=prob_id)
    except StoichiometryProblem.DoesNotExist:
        return StoichiometryProblem.objects.order_by('problem_id').first()


def _part_context(part: ProblemPart):
    """
    Build the template context variables that drive node rendering
    for a single ProblemPart.
    """
    nodes = part.expected_nodes()   # ordered list of {num_value, num_unit, den_value, den_unit}
    gf  = part.given_substance.formula
    tf  = part.target_substance.formula
    gq  = float(part.given_quantity)
    gu  = part.given_unit          # 'g' or 'mol'
    tu  = part.target_unit

    # Build the human-readable "starting node" label
    starting_label = f"{gq} {'g' if gu == 'g' else 'mol'} {gf}"
    target_label   = f"? {'g' if tu == 'g' else 'mol'} {tf}"

    return {
        'conversion_type':  part.conversion_type,
        'node_count':       part.node_count,
        'nodes_json':       json.dumps(nodes),   # consumed by JS
        'given_formula':    gf,
        'given_quantity':   gq,
        'given_unit':       gu,
        'target_formula':   tf,
        'target_unit':      tu,
        'starting_label':   starting_label,
        'target_label':     target_label,
        'correct_answer':   float(part.correct_answer),
        'part_label':       part.part_label,
        'part_prompt':      part.part_prompt,
    }

def _navigation_context(problem: StoichiometryProblem, current_part: ProblemPart):
    """
    Returns prev_part / next_part / all_parts for the module navigation bar
    along with dynamic routing targets.
    """
    all_parts = list(problem.parts.all())
    idx = next((i for i, p in enumerate(all_parts) if p.pk == current_part.pk), 0)

    prev_part = all_parts[idx - 1] if idx > 0 else None
    next_part = all_parts[idx + 1] if idx < len(all_parts) - 1 else None

    # Calculate exactly where the next part button should take the student
    next_part_url = None
    if next_part:
        if problem.is_limiting_problem and next_part.part_label in ['a', 'b', 'lane_a', 'lane_b']:
            # Parallel tracks (A and B) stay in Module 3 Limiting Workspace
            next_part_url = f'/limiting-workspace/{problem.problem_id}/{next_part.part_label}/'
        else:
            # Excess analytics (Part C) or any non-limiting part goes to Module 2 Step-Grid Workspace
            next_part_url = f'/workspace/{problem.problem_id}/{next_part.part_label}/'

    # Next problem boundaries (for after last part)
    all_problems = list(_all_problems())
    prob_idx = next((i for i, p in enumerate(all_problems) if p.pk == problem.pk), 0)
    next_problem = all_problems[prob_idx + 1] if prob_idx < len(all_problems) - 1 else None
    next_problem_first_part = (
        next_problem.parts.first() if next_problem else None
    )

    return {
        'all_parts':              all_parts,
        'current_part_idx':       idx,
        'prev_part':              prev_part,
        'next_part':              next_part,
        'next_part_url':          next_part_url,  # Injected cleanly into templates
        'next_problem':           next_problem,
        'next_problem_first_part': next_problem_first_part,
        'is_last_part':           next_part is None,
        'is_last_problem':        next_problem is None,
    }

# ---------------------------------------------------------------------------
# View: problem selection lobby
# ---------------------------------------------------------------------------

def problem_lobby(request):
    problems = list(_all_problems())
    context = {
        'problems': problems,
        'user_lvl': 1,
        'user_xp':  0,
    }
    return render(request, 'problem_lobby.html', context)


# ---------------------------------------------------------------------------
# View: Module 1 — Preparation Ledger
# ---------------------------------------------------------------------------

def preparation_ledger(request, prob_id=None):
    if prob_id:
        problem = _get_problem_or_first(prob_id)
    else:
        # Default: first problem
        problem = StoichiometryProblem.objects.order_by('problem_id').first()

    if not problem:
        return render(request, 'no_problems.html')

    # Parse reactant/product formula lists for the equation builder
    reactants = problem.reactants   # [{'coeff': 2, 'formula': 'H2'}, ...]
    products  = problem.products

    # Substances whose molar masses the student must look up
    all_formulas = [r['formula'] for r in reactants] + [p['formula'] for p in products]
    unique_formulas = list(dict.fromkeys(all_formulas))   # preserve order, deduplicate

    # First part (used in breadcrumb only)
    first_part = problem.parts.first()

    # Determine where "Lock & Proceed" sends the student dynamically
    if first_part:
        if first_part.part_label in ['lane_a', 'lane_b', 'a', 'b'] and problem.is_limiting_problem:
            # If it's a limiting reactant problem starting with its tracks, go to Module 3
            next_url = f'/limiting-workspace/{problem.problem_id}/{first_part.part_label}/'
        else:
            # Otherwise, go to the Module 2 Step-Grid Workspace
            next_url = f'/workspace/{problem.problem_id}/{first_part.part_label}/'
    else:
        next_url = f'/workspace/{problem.problem_id}/a/'

    context = {
        'problem_id':            problem.problem_id,
        'problem_title':         problem.title,
        'prompt':                problem.prompt,
        'reactants':             reactants,
        'products':              products,
        'target_substances':     unique_formulas,
        'correct_coefficients':  problem.correct_coefficients,
        'first_part_label':      first_part.part_label if first_part else 'a',
        'next_url':              next_url,
        'is_limiting_problem':   problem.is_limiting_problem,
        'all_problems':          list(_all_problems()),
        'user_lvl': 1,
        'user_xp':  320,
    }
    return render(request, 'module1_ledger.html', context)


# ---------------------------------------------------------------------------
# View: Module 2 — Step-Grid Workspace
# ---------------------------------------------------------------------------

def step_grid_workspace(request, prob_id, part_label='a'):
    problem = _get_problem_or_first(prob_id)
    if not problem:
        return render(request, 'no_problems.html')

    part = get_object_or_404(ProblemPart, problem=problem, part_label=part_label)

    context = {
        'problem_id':    problem.problem_id,
        'problem_title': problem.title,
        'prompt':        problem.prompt,
        **_part_context(part),
        **_navigation_context(problem, part),
        'user_lvl': 1,
        'user_xp':  370,
    }
    return render(request, 'module2_workspace.html', context)


# ---------------------------------------------------------------------------
# View: Module 3 — Limiting Reagent Workspace
# ---------------------------------------------------------------------------

def limiting_workspace(request, prob_id, part_label='a'):
    problem = _get_problem_or_first(prob_id)
    if not problem:
        return render(request, 'no_problems.html')

    part = get_object_or_404(ProblemPart, problem=problem, part_label=part_label)

    reactants = problem.reactants  # [{'coeff': N, 'formula': 'X'}, ...]

    # Per-reactant given quantities stored on the part (limiting problems only).
    # Fall back to part.given_quantity for every reactant if not set.
    lq = part.limiting_given_quantities or {}

    tracks = []
    from .models import Substance, _get_coeff
    for rxn_entry in reactants:
        formula = rxn_entry['formula']
        try:
            substance = Substance.objects.get(formula=formula)
        except Substance.DoesNotExist:
            continue

        first_product_formula = problem.products[0]['formula']
        try:
            target_sub = Substance.objects.get(formula=first_product_formula)
        except Substance.DoesNotExist:
            continue

        coeff_given  = rxn_entry['coeff']
        coeff_target = _get_coeff(problem, first_product_formula)

        # Use per-reactant quantity if available, otherwise fall back
        given_qty = float(lq.get(formula, part.given_quantity))

        tracks.append({
            'formula':           formula,
            'display_name':      substance.display_name,
            'molar_mass':        float(substance.molar_mass),
            'given_quantity':    given_qty,
            'coeff_given':       coeff_given,
            'coeff_target':      coeff_target,
            'target_formula':    first_product_formula,
            'target_molar_mass': float(target_sub.molar_mass),
        })

    context = {
        'problem_id':    problem.problem_id,
        'problem_title': problem.title,
        'prompt':        problem.prompt,
        'tracks_json':   json.dumps(tracks),
        **_part_context(part),
        **_navigation_context(problem, part),
        'user_lvl': 1,
        'user_xp':  470,
    }
    return render(request, 'module3_limiting.html', context)

"""
Module 4: Student-Facing Telemetry Analytics & Performance Dashboard
"""
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

# ---------------------------------------------------------------------------
# API: Verify balancing (called from Module 1 JS via fetch)
# ---------------------------------------------------------------------------

@csrf_exempt
def verify_balancing_backend(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'})

    data     = json.loads(request.body)
    prob_id  = data.get('problem_id', '')
    submitted = data.get('coefficients', [])   # e.g. ['2', '1', '2']

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
        log.save()

        return JsonResponse({
            'success':  is_correct,
            'attempts': log.attempts_count,
            'message':  (
                'Chamber Stabilized! Reaction is perfectly balanced.'
                if is_correct else
                'Reaction Imbalance Detected! Try checking atom ratios.'
            ),
        })

    except StoichiometryProblem.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Problem not found.'})


# ---------------------------------------------------------------------------
# API: Validate a single step-node answer
# ---------------------------------------------------------------------------

@csrf_exempt
def validate_step_node(request):
    """
    POST  { problem_id, part_label, node_index, num_value, num_unit,
            den_value, den_unit }
    Returns  { success, message, expected_num, expected_den }
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method.'})

    data       = json.loads(request.body)
    prob_id    = data.get('problem_id')
    part_label = data.get('part_label', 'a')
    node_idx   = int(data.get('node_index', 0))   # 0-based

    try:
        problem = StoichiometryProblem.objects.get(problem_id=prob_id)
        part    = ProblemPart.objects.get(problem=problem, part_label=part_label)
    except (StoichiometryProblem.DoesNotExist, ProblemPart.DoesNotExist):
        return JsonResponse({'success': False, 'message': 'Problem or part not found.'})

    nodes = part.expected_nodes()
    if node_idx >= len(nodes):
        return JsonResponse({'success': False, 'message': 'Node index out of range.'})

    expected = nodes[node_idx]
    TOLERANCE = 0.01

    # Guard: return early if inputs are null/NaN (empty form submission)
    try:
        num_val = float(data.get('num_value'))
        den_val = float(data.get('den_value'))
    except (TypeError, ValueError):
        return JsonResponse({
            'success': False,
            'message': 'Empty or invalid input — fill in both fields before submitting.',
        })

    num_ok = abs(num_val - expected['num_value']) < TOLERANCE
    num_u  = data.get('num_unit', '').strip() == expected['num_unit']
    den_ok = abs(den_val - expected['den_value']) < TOLERANCE
    den_u  = data.get('den_unit', '').strip() == expected['den_unit']

    is_correct = num_ok and num_u and den_ok and den_u

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
    log.save()

    return JsonResponse({
        'success': is_correct,
        'message': (
            f'Node {node_idx + 1} verified! Units cancel correctly.'
            if is_correct else
            'Incorrect — check values and unit labels.'
        ),
        'expected_num_value': expected['num_value'],
        'expected_num_unit':  expected['num_unit'],
        'expected_den_value': expected['den_value'],
        'expected_den_unit':  expected['den_unit'],
    })