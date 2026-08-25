from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from .models import (
    Substance, StoichiometryProblem, ProblemPart,
    StudentTelemetryLog, ProblemProgress, PartProgress,
)
from .views import _m1_accuracy


class BaseFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        for formula, mass in [('H', 1.008), ('O', 15.999),
                              ('H2', 2.016), ('O2', 31.998), ('H2O', 18.015)]:
            Substance.objects.create(formula=formula, display_name=formula,
                                     molar_mass=mass)

        cls.plain = StoichiometryProblem.objects.create(
            problem_id='P_TST',
            title='Water synthesis drill',
            prompt='Test',
            reactants_str='2:H2,1:O2',
            products_str='2:H2O',
            correct_coefficients='2,1,2',
            is_limiting_problem=False,
        )
        ProblemPart.objects.create(
            problem=cls.plain, part_label='a',
            part_prompt='Convert 10 g H2 to H2O.',
            given_substance_id='H2', given_quantity=Decimal('10'),
            given_unit='g', target_substance_id='H2O', target_unit='g',
            conversion_type='g_to_g',
            correct_answer=Decimal('89.3571'), order=0,
        )

        cls.limiting = StoichiometryProblem.objects.create(
            problem_id='P_LIM',
            title='Limiting drill',
            prompt='Test limiting',
            reactants_str='2:H2,1:O2',
            products_str='2:H2O',
            correct_coefficients='2,1,2',
            is_limiting_problem=True,
        )
        ProblemPart.objects.create(
            problem=cls.limiting, part_label='a',
            part_prompt='Track A: from 4 g H2.',
            given_substance_id='H2', given_quantity=Decimal('4'),
            given_unit='g', target_substance_id='H2O', target_unit='g',
            conversion_type='g_to_g',
            correct_answer=Decimal('35.7429'), order=0,
        )
        ProblemPart.objects.create(
            problem=cls.limiting, part_label='b',
            part_prompt='Track B: from 32 g O2.',
            given_substance_id='O2', given_quantity=Decimal('32'),
            given_unit='g', target_substance_id='H2O', target_unit='g',
            conversion_type='g_to_g',
            correct_answer=Decimal('36.0338'), order=1,
        )

        cls.user = User.objects.create_user('student1', password='pass12345')
        cls.other = User.objects.create_user('student2', password='pass12345')

    def login(self, user=None):
        user = user or self.user
        client = Client()
        client.force_login(user)
        return client


def _nodes_payload(part, override=None):
    nodes = []
    for n in part.expected_nodes():
        item = {
            'num_value': str(n['num_value']),
            'num_unit': n['num_unit'],
            'den_value': str(n['den_value']),
            'den_unit': n['den_unit'],
        }
        if override:
            override(item)
        nodes.append(item)
    return nodes


def complete_module1(client, prob_id='P_TST', perfect=True):
    checkpoint = client.post(reverse('m1_checkpoint'),
                             {'problem_id': prob_id, 'choice': 'H2'},
                             content_type='application/json')
    balance = client.post(reverse('verify_balancing'),
                          {'problem_id': prob_id, 'coefficients': [2, 1, 2]},
                          content_type='application/json')
    masses = {'H2': 2.016, 'O2': 31.998, 'H2O': 18.015}
    if not perfect:
        masses['H2O'] = 55.0
    molar = client.post(reverse('verify_molar_mass'),
                        {'problem_id': prob_id, 'molar_masses': masses},
                        content_type='application/json')
    retrieval_challenge = client.get(f'/api/m1-retrieval/?problem_id={prob_id}')
    formula = retrieval_challenge.json()['formula']
    from .models import Substance as S
    correct_value = S.objects.get(formula=formula).molar_mass
    if not perfect:
        correct_value += 40
    retrieval = client.post(reverse('m1_retrieval'),
                            {'problem_id': prob_id, 'formula': formula,
                             'value': correct_value},
                            content_type='application/json')
    return checkpoint, balance, molar, retrieval


class Module1GateTests(BaseFixture):
    def test_checkpoint_accepts_diatomic_answer(self):
        client = self.login()
        resp = client.post(reverse('m1_checkpoint'),
                           {'problem_id': 'P_TST', 'choice': 'O2'},
                           content_type='application/json').json()
        self.assertTrue(resp['success'])
        progress = ProblemProgress.objects.get(user=self.user, problem_id='P_TST')
        self.assertTrue(progress.checkpoint_cleared)

    def test_checkpoint_rejects_wrong_choice(self):
        client = self.login()
        resp = client.post(reverse('m1_checkpoint'),
                           {'problem_id': 'P_TST', 'choice': 'H2O'},
                           content_type='application/json').json()
        self.assertFalse(resp['success'])

    def test_scaled_tolerance_tight_for_simple_formulas(self):
        client = self.login()
        masses = {'H2': 2.6, 'O2': 31.998, 'H2O': 18.015}
        resp = client.post(reverse('verify_molar_mass'),
                           {'problem_id': 'P_TST', 'molar_masses': masses},
                           content_type='application/json').json()
        self.assertFalse(resp['success'])
        self.assertFalse(resp['results']['H2']['correct'])

    def test_perfect_run_passes_accuracy_gate(self):
        client = self.login()
        complete_module1(client)
        progress = ProblemProgress.objects.get(user=self.user, problem_id='P_TST')
        acc, _, tries = _m1_accuracy(self.user, 'P_TST')
        self.assertEqual(acc, 100.0)
        self.assertTrue(progress.accuracy_gate_passed)

    def test_imperfect_run_blocks_accuracy_gate(self):
        client = self.login()
        checkpoint, balance, molar, retrieval = complete_module1(client, perfect=False)
        self.assertFalse(molar.json()['success'])
        masses = {'H2': 2.016, 'O2': 31.998, 'H2O': 18.015}
        molar2 = client.post(reverse('verify_molar_mass'),
                             {'problem_id': 'P_TST', 'molar_masses': masses},
                             content_type='application/json').json()
        self.assertTrue(molar2['success'])
        progress = ProblemProgress.objects.get(user=self.user, problem_id='P_TST')
        acc, _, tries = _m1_accuracy(self.user, 'P_TST')
        self.assertLess(acc, 80)
        self.assertFalse(progress.accuracy_gate_passed)

    def test_workspace_blocked_without_module1_completion(self):
        client = self.login()
        resp = client.get(reverse('step_grid_workspace',
                                  args=['P_TST', 'a']), follow=True)
        self.assertRedirects(resp, reverse('preparation_ledger',
                                           args=['P_TST']))

    def test_workspace_accessible_after_full_module1(self):
        client = self.login()
        complete_module1(client)
        progress = ProblemProgress.objects.get(user=self.user, problem_id='P_TST')
        progress.checkpoint_cleared = True
        progress.retrieval_check_passed = True
        progress.accuracy_gate_passed = True
        progress.balancing_cleared = True
        progress.molar_mass_cleared = True
        progress.save()
        resp = client.get(reverse('step_grid_workspace', args=['P_TST', 'a']))
        self.assertEqual(resp.status_code, 200)

    def test_no_answer_keys_in_ledger_html(self):
        client = self.login()
        html = client.get(reverse('preparation_ledger', args=['P_TST'])).content.decode()
        self.assertNotIn('correct_coefficients', html)
        self.assertIn('PROGRESS', html)


class MolarMassHintTests(BaseFixture):
    def test_coefficient_trap_hint_returned(self):
        client = self.login()
        client.post(reverse('m1_checkpoint'),
                    {'problem_id': 'P_TST', 'choice': 'O2'},
                    content_type='application/json')
        client.post(reverse('verify_balancing'),
                    {'problem_id': 'P_TST', 'coefficients': [2, 1, 2]},
                    content_type='application/json')
        resp = client.post(reverse('verify_molar_mass'),
                           {'problem_id': 'P_TST',
                            'molar_masses': {'H2': 4.032, 'O2': 31.998, 'H2O': 18.015}},
                           content_type='application/json').json()
        self.assertFalse(resp['success'])
        self.assertIn('balancing coefficient', resp['hint'])


class ChainAuditTests(BaseFixture):
    def setUp(self):
        self.client_inst = self.login()
        progress = ProblemProgress.get_or_default(self.user, 'P_TST')
        progress.checkpoint_cleared = True
        progress.balancing_cleared = True
        progress.molar_mass_cleared = True
        progress.retrieval_check_passed = True
        progress.accuracy_gate_passed = True
        progress.save()

    def test_correct_chain_succeeds_and_persists(self):
        part = ProblemPart.objects.get(problem__problem_id='P_TST', part_label='a')
        payload = {'problem_id': 'P_TST', 'part_label': 'a',
                   'nodes': _nodes_payload(part)}
        resp = self.client_inst.post(reverse('audit_chain'), payload,
                                     content_type='application/json').json()
        self.assertTrue(resp['success'])
        pp = PartProgress.objects.get(user=self.user, problem_id='P_TST', part_label='a')
        self.assertTrue(pp.lane_cleared)
        self.assertEqual(len(pp.chain_json), 3)

    def test_wrong_units_reported_separately_from_values(self):
        part = ProblemPart.objects.get(problem__problem_id='P_TST', part_label='a')
        expected = part.expected_nodes()

        def break_units(item):
            item['den_unit'] = 'g_H2O'

        payload = {'problem_id': 'P_TST', 'part_label': 'a',
                   'nodes': _nodes_payload(part, break_units)}
        resp = self.client_inst.post(reverse('audit_chain'), payload,
                                     content_type='application/json').json()
        self.assertFalse(resp['success'])
        self.assertFalse(resp['reports'][0]['unit_ok'])

    def test_wrong_values_with_right_units_isolated(self):
        part = ProblemPart.objects.get(problem__problem_id='P_TST', part_label='a')

        def break_values(item):
            item['num_value'] = '999'

        payload = {'problem_id': 'P_TST', 'part_label': 'a',
                   'nodes': _nodes_payload(part, break_values)}
        resp = self.client_inst.post(reverse('audit_chain'), payload,
                                     content_type='application/json').json()
        self.assertFalse(resp['success'])
        self.assertTrue(resp['matched_units'])
        self.assertFalse(resp['reports'][0]['value_ok'])

    def test_step_lock_engages_on_low_rolling_accuracy(self):
        from django.utils import timezone
        for i in range(5):
            StudentTelemetryLog.objects.create(
                user=self.user, problem_id='P_TST', part_label='a',
                sub_step=str(i), module_phase=2,
                is_correct=False, attempts_count=1,
            )
        StudentTelemetryLog.objects.create(
            user=self.user, problem_id='P_TST', part_label='a',
            sub_step='9', module_phase=2, is_correct=False, attempts_count=1,
            created_at=timezone.now(),
        )
        part = ProblemPart.objects.get(problem__problem_id='P_TST', part_label='a')
        payload = {'problem_id': 'P_TST', 'part_label': 'a',
                   'nodes': _nodes_payload(part)}
        resp = self.client_inst.post(reverse('audit_chain'), payload,
                                     content_type='application/json').json()
        self.assertTrue(resp.get('locked'))
        self.assertGreater(resp.get('retry_after', 0), 0)


class LimitingWorkspaceTests(BaseFixture):
    def complete_m1_for_limiting(self):
        client = self.login()
        checkpoint, balance, molar, retrieval = complete_module1(client, prob_id='P_LIM')
        assert checkpoint.json()['success'], f'checkpoint: {checkpoint.json()}'
        assert balance.json()['success'], f'balance: {balance.json()}'
        assert molar.json()['success'], f'molar: {molar.json()}'
        assert retrieval.json()['success'], f'retrieval: {retrieval.json()}'
        p = ProblemProgress.objects.get(user=self.user, problem_id='P_LIM')
        p.accuracy_gate_passed = True
        p.save()
        return client

    def clear_lane(self, client, label):
        part = ProblemPart.objects.get(problem__problem_id='P_LIM', part_label=label)
        payload = {'action': 'verify_lane', 'part_label': label,
                   'nodes': _nodes_payload(part)}
        resp = client.post(reverse('limiting_workspace', args=['P_LIM']),
                           payload, content_type='application/json')
        if resp['Content-Type'] != 'application/json':
            raise AssertionError(
                f'clear_lane got {resp.status_code} → {resp.get("Location", "")} '
                f'{resp.content[:200]}')
        return resp.json()

    def test_deduction_requires_comparison_first(self):
        client = self.complete_m1_for_limiting()
        self.clear_lane(client, 'a')
        self.clear_lane(client, 'b')
        resp = client.post(reverse('limiting_workspace', args=['P_LIM']),
                           {'action': 'verify_deduction',
                            'limiting_reagent': 'H2',
                            'theoretical_yield': '35.7429',
                            'excess_remaining': {}},
                           content_type='application/json').json()
        self.assertFalse(resp['success'])
        self.assertIn('comparison', resp['message'].lower())

    def test_full_flow_including_excess_remaining(self):
        client = self.complete_m1_for_limiting()
        self.clear_lane(client, 'a')
        self.clear_lane(client, 'b')

        comparison = client.post(reverse('limiting_workspace', args=['P_LIM']),
                                 {'action': 'verify_comparison', 'choice_track': 'a'},
                                 content_type='application/json').json()
        self.assertTrue(comparison['success'])

        moles_h2 = 4 / 2.016
        moles_o2_start = 32 / 31.998
        moles_o2_used = moles_h2 * (1 / 2)
        excess_left = (moles_o2_start - moles_o2_used) * 31.998

        deduction = client.post(reverse('limiting_workspace', args=['P_LIM']),
                                {'action': 'verify_deduction',
                                 'limiting_reagent': 'H2',
                                 'theoretical_yield': '35.7429',
                                 'excess_remaining': {'O2': f'{excess_left:.4f}'}},
                                content_type='application/json').json()
        self.assertTrue(deduction['success'])

    def test_wrong_excess_flagged_by_formula(self):
        client = self.complete_m1_for_limiting()
        self.clear_lane(client, 'a')
        self.clear_lane(client, 'b')
        client.post(reverse('limiting_workspace', args=['P_LIM']),
                    {'action': 'verify_comparison', 'choice_track': 'a'},
                    content_type='application/json')
        resp = client.post(reverse('limiting_workspace', args=['P_LIM']),
                           {'action': 'verify_deduction',
                            'limiting_reagent': 'H2',
                            'theoretical_yield': '35.7429',
                            'excess_remaining': {'O2': '999'}},
                           content_type='application/json').json()
        self.assertFalse(resp['success'])
        self.assertIn('O2', resp['message'])

    def test_hint_escalation_after_three_failures(self):
        client = self.complete_m1_for_limiting()
        self.clear_lane(client, 'a')
        self.clear_lane(client, 'b')
        client.post(reverse('limiting_workspace', args=['P_LIM']),
                    {'action': 'verify_comparison', 'choice_track': 'a'},
                    content_type='application/json')
        hints = []
        for _ in range(3):
            resp = client.post(reverse('limiting_workspace', args=['P_LIM']),
                               {'action': 'verify_deduction',
                                'limiting_reagent': 'O2',
                                'theoretical_yield': '36.0338',
                                'excess_remaining': {}},
                               content_type='application/json').json()
            hints.append(resp.get('hint', ''))
        self.assertTrue(hints[2])
        self.assertIn('limiting reagent', hints[2].lower())


class DashboardTests(BaseFixture):
    def test_dashboard_scoped_to_requesting_user_only(self):
        StudentTelemetryLog.objects.create(
            user=self.user, problem_id='P_TST', part_label='balance',
            sub_step='1A', module_phase=1, is_correct=True, attempts_count=0)
        other_log = StudentTelemetryLog.objects.create(
            user=self.other, problem_id='P_TST', part_label='balance',
            sub_step='1A', module_phase=1, is_correct=True, attempts_count=0)
        other_log.attempts_count = 7
        other_log.save()

        client = self.login()
        resp = client.get(reverse('student_dashboard'))
        self.assertEqual(resp.context['total_attempts'], 0)

    def test_pdf_export_returns_pdf_bytes(self):
        client = self.login()
        resp = client.get(reverse('dashboard_export_pdf'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content.startswith(b'%PDF'))

    def test_instructor_dashboard_staff_only(self):
        staff = User.objects.create_user('teacher', password='pass12345',
                                         is_staff=True)
        staff_client = Client()
        staff_client.force_login(staff)
        resp = staff_client.get(reverse('instructor_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('student1', resp.content.decode())

        student_client = self.login()
        resp2 = student_client.get(reverse('instructor_dashboard'))
        self.assertNotEqual(resp2.status_code, 200)


class ResetTests(BaseFixture):
    def test_reset_clears_progress_rows(self):
        client = self.login()
        ProblemProgress.get_or_default(self.user, 'P_TST')
        PartProgress.get_or_default(self.user, 'P_TST', 'a')
        client.post(reverse('verify_balancing'),
                    {'problem_id': 'P_TST', 'coefficients': [2, 1, 2]},
                    content_type='application/json')
        client.get(reverse('reset_problem_telemetry', args=['P_TST']))
        self.assertFalse(ProblemProgress.objects.filter(
            user=self.user, problem_id='P_TST').exists())
        self.assertFalse(PartProgress.objects.filter(
            user=self.user, problem_id='P_TST').exists())
        self.assertFalse(StudentTelemetryLog.objects.filter(
            user=self.user, problem_id='P_TST').exists())


class SynthesisTests(BaseFixture):
    def test_locked_before_five_completions(self):
        client = self.login()
        resp = client.get(reverse('synthesis_challenge'), follow=True)
        self.assertRedirects(resp, reverse('problem_lobby'))

    def test_submit_grades_items(self):
        from django.utils import timezone
        client = self.login()
        for pid in ['S1', 'S2', 'S3', 'S4', 'S5']:
            problem = StoichiometryProblem.objects.create(
                problem_id=pid, title=f'T{pid}', prompt='x',
                reactants_str='2:H2,1:O2', products_str='2:H2O',
                correct_coefficients='2,1,2')
            ProblemPart.objects.create(
                problem=problem, part_label='a', part_prompt='x',
                given_substance_id='H2', given_quantity=Decimal('10'),
                given_unit='g', target_substance_id='H2O', target_unit='g',
                conversion_type='mol_to_mol',
                correct_answer=Decimal('10'))
            ProblemProgress.objects.create(
                user=self.user, problem_id=pid,
                balancing_cleared=True, molar_mass_cleared=True,
                checkpoint_cleared=True, retrieval_check_passed=True,
                accuracy_gate_passed=True)
        part_a = ProblemPart.objects.get(problem__problem_id='S1', part_label='a')
        good_nodes = [{'num_value': str(n['num_value']),
                       'num_unit': n['num_unit'],
                       'den_value': str(n['den_value']),
                       'den_unit': n['den_unit']}
                      for n in part_a.expected_nodes()]
        bad_nodes = [dict(good_nodes[0]), ]
        bad_nodes[0]['num_unit'] = 'g_H2O'

        resp = client.post(reverse('synthesis_submit'),
                           {'answers': [
                               {'problem_id': 'S1', 'part_label': 'a',
                                'nodes': good_nodes},
                               {'problem_id': 'S2', 'part_label': 'a',
                                'nodes': bad_nodes + good_nodes[:0]},
                           ]},
                           content_type='application/json').json()
        self.assertTrue(resp['success'])
