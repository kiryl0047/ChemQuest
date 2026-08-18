import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from .models import StoichiometryProblem, Substance, StudentTelemetryLog

class Module1TelemetryTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='teststudent', password='password123')
        self.client.login(username='teststudent', password='password123')

        # Create substances
        self.sub_h2 = Substance.objects.create(formula='H2', display_name='Hydrogen gas', molar_mass=2.016)
        self.sub_o2 = Substance.objects.create(formula='O2', display_name='Oxygen gas', molar_mass=31.998)
        self.sub_h2o = Substance.objects.create(formula='H2O', display_name='Water', molar_mass=18.015)

        # Create problem
        self.problem = StoichiometryProblem.objects.create(
            problem_id='PROB-01',
            title='Synthesis of Water',
            prompt='Combine hydrogen and oxygen gas to form water.',
            reactants_str='2:H2,1:O2',
            products_str='2:H2O',
            correct_coefficients='2,1,2',
            is_limiting_problem=False
        )

    def test_sub_step_1a_balancing_correct(self):
        response = self.client.post(
            '/api/verify-balancing/',
            data=json.dumps({'problem_id': 'PROB-01', 'coefficients': ['2', '1', '2']}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        log = StudentTelemetryLog.objects.get(problem_id='PROB-01', part_label='balance')
        self.assertEqual(log.sub_step, '1A')
        self.assertEqual(log.module_phase, 1)
        self.assertTrue(log.is_correct)
        self.assertEqual(log.user, self.user)

    def test_sub_step_1a_balancing_incorrect(self):
        response = self.client.post(
            '/api/verify-balancing/',
            data=json.dumps({'problem_id': 'PROB-01', 'coefficients': ['1', '1', '1']}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Reaction Imbalance', data['message'])
        self.assertTrue(len(data.get('hint', '')) > 0)

        log = StudentTelemetryLog.objects.get(problem_id='PROB-01', part_label='balance')
        self.assertEqual(log.sub_step, '1A')
        self.assertFalse(log.is_correct)
        self.assertEqual(log.attempts_count, 1)

    def test_sub_step_1a_multiple_ratio_trap(self):
        response = self.client.post(
            '/api/verify-balancing/',
            data=json.dumps({'problem_id': 'PROB-01', 'coefficients': ['4', '2', '4']}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('SIMPLEST whole-number integer ratio', data['message'])
        self.assertIn('Divide each coefficient by 2', data['hint'])

    def test_sub_step_1b_molar_mass_correct(self):
        response = self.client.post(
            '/api/verify-molar-mass/',
            data=json.dumps({
                'problem_id': 'PROB-01',
                'molar_masses': {
                    'H2': '2.016',
                    'O2': '31.998',
                    'H2O': '18.015'
                }
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['results']['H2']['correct'])
        self.assertTrue(data['results']['O2']['correct'])
        self.assertTrue(data['results']['H2O']['correct'])

        log = StudentTelemetryLog.objects.get(problem_id='PROB-01', part_label='molar_mass')
        self.assertEqual(log.sub_step, '1B')
        self.assertEqual(log.module_phase, 1)
        self.assertTrue(log.is_correct)
        self.assertEqual(log.user, self.user)

    def test_sub_step_1b_molar_mass_partial_mismatch(self):
        response = self.client.post(
            '/api/verify-molar-mass/',
            data=json.dumps({
                'problem_id': 'PROB-01',
                'molar_masses': {
                    'H2': '2.016',
                    'O2': '16.000', # wrong (should be 31.998)
                    'H2O': '18.015'
                }
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertTrue(data['results']['H2']['correct'])
        self.assertFalse(data['results']['O2']['correct'])
        self.assertTrue(data['results']['H2O']['correct'])
        self.assertIn('For O2', data.get('hint', ''))

        log = StudentTelemetryLog.objects.get(problem_id='PROB-01', part_label='molar_mass')
        self.assertEqual(log.sub_step, '1B')
        self.assertFalse(log.is_correct)
        self.assertEqual(log.attempts_count, 1)
