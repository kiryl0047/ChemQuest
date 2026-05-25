from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import StoichiometryProblem, StudentTelemetryLog

def preparation_ledger(request):
    # Dummy problem parameters for development/demo testing
    context = {
        'problem_id': 'PROB_101',
        'prompt': 'How many grams of water (H2O) are produced from the complete reaction of 15.0 grams of Hydrogen gas (H2) with excess Oxygen gas (O2)?',
        'unbalanced_equation': {
            'reactants': [
                {'formula': 'H2', 'placeholder': '?'},
                {'formula': 'O2', 'placeholder': '?'}
            ],
            'products': [
                {'formula': 'H2O', 'placeholder': '?'}
            ]
        },
        'target_substances': ['H2', 'H2O'], # Elements requiring molar mass calculation
        'user_lvl': 1,
        'user_xp': 320
    }
    return render(request, 'module1_ledger.html', context)

def step_grid_workspace(request, prob_id):
    try:
        problem = StoichiometryProblem.objects.get(problem_id=prob_id)
    except StoichiometryProblem.DoesNotExist:
        problem = StoichiometryProblem.objects.first() # Fallback safe guard

    context = {
        'problem_id': problem.problem_id,
        'prompt': problem.prompt,
        'reactant_mass': problem.reactant_a_mass,
        'product_mass': problem.product_mass,
        'user_lvl': 1,
        'user_xp': 370 # Updated XP reward from clearing Module 1!
    }
    return render(request, 'module2_workspace.html', context)

def limiting_workspace(request, prob_id):
    try:
        problem = StoichiometryProblem.objects.get(problem_id=prob_id)
    except StoichiometryProblem.DoesNotExist:
        problem = StoichiometryProblem.objects.first()

    context = {
        'problem_id': problem.problem_id,
        'prompt': problem.prompt,
        'reactant_a_mass': problem.reactant_a_mass, # H2: 2.016
        'reactant_b_mass': 31.998,                  # O2 Molar Mass (Added for Module 3)
        'product_mass': problem.product_mass,       # H2O: 18.015
        'user_lvl': 1,
        'user_xp': 470                               # Accumulated XP up to Module 3
    }
    return render(request, 'module3_limiting.html', context)

@csrf_exempt # This temporarily bypasses CSRF safety so your local demo fetch requests pass smoothly
def verify_balancing_backend(request):
    if request.method == 'POST':
        # 1. Parse the incoming JSON data from the browser
        data = json.loads(request.body)
        prob_id = data.get('problem_id')
        r0 = data.get('r0')
        r1 = data.get('r1')
        p0 = data.get('p0')

        try:
            # 2. Grab our local seed problem (PROB_101) from the database
            problem = StoichiometryProblem.objects.get(problem_id=prob_id)
            
            # 3. Read the expected coefficients string ("2,1,2") and split it into an array
            expected = problem.correct_coefficients.split(',')
            
            # 4. Perform the logic check: Does the student input match the correct answer?
            is_correct = (r0 == expected[0] and r1 == expected[1] and p0 == expected[2])

            # 5. Log this attempt into our local StudentTelemetryLog table
            log, created = StudentTelemetryLog.objects.get_or_create(
                problem_id=prob_id,
                module_phase=1,
                defaults={'attempts_count': 0}
            )
            log.attempts_count += 1
            log.is_correct = is_correct
            log.save()

            # 6. Return the results back to the browser as a JSON payload
            return JsonResponse({
                'success': is_correct,
                'attempts': log.attempts_count,
                'message': 'Chamber Stabilized! Reaction is perfectly balanced.' if is_correct else 'Reaction Imbalance Detected! Try checking atom ratios.'
            })
            
        except StoichiometryProblem.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Problem ID not found in local database.'})

    return JsonResponse({'success': False, 'message': 'Invalid Request Method.'})