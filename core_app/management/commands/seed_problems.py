"""
python manage.py seed_problems

Seeds the database with:
  • All required Substance records
  • StoichiometryProblem records
  • ProblemPart records for every sub-question

Run this once after applying migrations.
"""
from django.core.management.base import BaseCommand
from core_app.models import (
    Substance, StoichiometryProblem, ProblemPart,
    CONVERSION_MOL_TO_MOL, CONVERSION_MOL_TO_G,
    CONVERSION_G_TO_MOL, CONVERSION_G_TO_G,
)


# ---------------------------------------------------------------------------
# Master substance registry  (IUPAC molar masses)
# ---------------------------------------------------------------------------
SUBSTANCES = [
    # formula        display_name                      molar_mass
    ('H2',    'Hydrogen Gas',                          2.0160),
    ('O2',    'Oxygen Gas',                           31.9988),
    ('H2O',   'Water',                                18.0153),
    ('SO2',   'Sulfur Dioxide',                       64.0638),
    ('SO3',   'Sulfur Trioxide',                      80.0632),
    ('C3H8',  'Propane',                              44.0956),
    ('CO2',   'Carbon Dioxide',                       44.0095),
    ('Al',    'Aluminum',                             26.9815),
    ('Cl2',   'Chlorine Gas',                         70.9060),
    ('AlCl3', 'Aluminum Chloride',                   133.3405),
]


# ---------------------------------------------------------------------------
# Problem seed data
# ---------------------------------------------------------------------------
PROBLEMS = [

    # -----------------------------------------------------------------------
    # PROB_101  –  H2 + O2 → H2O
    # -----------------------------------------------------------------------
    {
        'problem_id':  'PROB_101',
        'title':       'Hydrogen Combustion',
        'prompt':      (
            'Hydrogen gas (H₂) reacts with Oxygen gas (O₂) to produce Water (H₂O). '
            'Given 15.0 g of H₂ reacting with excess O₂, determine the theoretical '
            'yield of water.'
        ),
        'reactants_str':       '2:H2,1:O2',
        'products_str':        '2:H2O',
        'correct_coefficients':'2,1,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'How many grams of H₂O are produced from 15.0 g of H₂ (excess O₂)?',
                'given_formula':   'H2',
                'given_quantity':  15.0,
                'given_unit':      'g',
                'target_formula':  'H2O',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                # (15.0 / 2.016) × (2/2) × 18.015 = 134.04 g
                'correct_answer':  134.0424,
            },
        ],
    },

    # -----------------------------------------------------------------------
    # PROB_201  –  SO2 + O2 → SO3
    # 2 SO2 + O2 → 2 SO3
    # -----------------------------------------------------------------------
    {
        'problem_id':  'PROB_201',
        'title':       'Sulfur Dioxide Oxidation',
        'prompt':      (
            'Sulfur Dioxide (SO₂) reacts with Oxygen gas (O₂) to form Sulfur Trioxide (SO₃). '
            '2 SO₂ + O₂ → 2 SO₃'
        ),
        'reactants_str':       '2:SO2,1:O2',
        'products_str':        '2:SO3',
        'correct_coefficients':'2,1,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     '(a) If 3.4 mol of SO₂ reacts with excess O₂, how many moles of SO₃ will form?',
                'given_formula':   'SO2',
                'given_quantity':  3.4,
                'given_unit':      'mol',
                'target_formula':  'SO3',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_MOL_TO_MOL,
                # 3.4 × (2/2) = 3.4 mol SO3
                'correct_answer':  3.4000,
            },
            {
                'part_label':      'b',
                'part_prompt':     '(b) How many moles of O₂ will react completely with 4.7 mol of SO₂?',
                'given_formula':   'SO2',
                'given_quantity':  4.7,
                'given_unit':      'mol',
                'target_formula':  'O2',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_MOL_TO_MOL,
                # 4.7 × (1/2) = 2.35 mol O2
                'correct_answer':  2.3500,
            },
        ],
    },

    # -----------------------------------------------------------------------
    # PROB_301  –  C3H8 + O2 → CO2 + H2O
    # C3H8 + 5 O2 → 3 CO2 + 4 H2O
    # -----------------------------------------------------------------------
    {
        'problem_id':  'PROB_301',
        'title':       'Propane Combustion',
        'prompt':      (
            'Propane (C₃H₈) reacts with Oxygen gas (O₂) to form Carbon Dioxide (CO₂) '
            'and Water (H₂O). '
            'C₃H₈ + 5 O₂ → 3 CO₂ + 4 H₂O'
        ),
        'reactants_str':       '1:C3H8,5:O2',
        'products_str':        '3:CO2,4:H2O',
        'correct_coefficients':'1,5,3,4',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     '(a) If 2.8 mol of C₃H₈ reacts with excess O₂, how many grams of CO₂ will form?',
                'given_formula':   'C3H8',
                'given_quantity':  2.8,
                'given_unit':      'mol',
                'target_formula':  'CO2',
                'target_unit':     'g',
                'conversion_type': CONVERSION_MOL_TO_G,
                # 2.8 × (3/1) × 44.010 = 369.68 g
                'correct_answer':  369.6798,
            },
            {
                'part_label':      'b',
                'part_prompt':     '(b) How many grams of O₂ will completely react with 3.8 mol of C₃H₈?',
                'given_formula':   'C3H8',
                'given_quantity':  3.8,
                'given_unit':      'mol',
                'target_formula':  'O2',
                'target_unit':     'g',
                'conversion_type': CONVERSION_MOL_TO_G,
                # 3.8 × (5/1) × 31.9988 = 607.9772 g
                'correct_answer':  607.9772,
            },
            {
                'part_label':      'c',
                'part_prompt':     '(c) If 25.0 g of C₃H₈ reacts with excess O₂, how many moles of H₂O will form?',
                'given_formula':   'C3H8',
                'given_quantity':  25.0,
                'given_unit':      'g',
                'target_formula':  'H2O',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_G_TO_MOL,
                # (25.0 / 44.0956) × (4/1) = 2.2678 mol
                'correct_answer':  2.2678,
            },
            {
                'part_label':      'd',
                'part_prompt':     '(d) If 38.0 g of H₂O are produced, how many moles of CO₂ were produced?',
                'given_formula':   'H2O',
                'given_quantity':  38.0,
                'given_unit':      'g',
                'target_formula':  'CO2',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_G_TO_MOL,
                # (38.0 / 18.015) × (3/4) = 1.582 mol
                'correct_answer':  1.5820,
            },
        ],
    },

    # -----------------------------------------------------------------------
    # PROB_401  –  Al + Cl2 → AlCl3
    # 2 Al + 3 Cl2 → 2 AlCl3
    # -----------------------------------------------------------------------
    {
        'problem_id':  'PROB_401',
        'title':       'Aluminum Chloride Synthesis',
        'prompt':      (
            'Aluminum (Al) reacts with Chlorine gas (Cl₂) to form Aluminum Chloride (AlCl₃). '
            '2 Al + 3 Cl₂ → 2 AlCl₃'
        ),
        'reactants_str':       '2:Al,3:Cl2',
        'products_str':        '2:AlCl3',
        'correct_coefficients':'2,3,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     '(a) If 35.0 g of Al reacts with excess Cl₂, how many grams of AlCl₃ will form?',
                'given_formula':   'Al',
                'given_quantity':  35.0,
                'given_unit':      'g',
                'target_formula':  'AlCl3',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                # (35.0/26.9815)×(2/2)×133.3405 = 172.9673 g
                'correct_answer':  172.9673,
            },
            {
                'part_label':      'b',
                'part_prompt':     '(b) How many grams of Cl₂ will react completely with 42.8 g of Al?',
                'given_formula':   'Al',
                'given_quantity':  42.8,
                'given_unit':      'g',
                'target_formula':  'Cl2',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                # (42.8/26.9815)×(3/2)×70.9060 = 168.7143 g
                'correct_answer':  168.7143,
            },
        ],
    },

]


class Command(BaseCommand):
    help = 'Seed the database with all ChemQuest sample problems and substances.'

    def handle(self, *args, **options):
        self.stdout.write('--- Seeding Substances ---')
        substance_map = {}
        for formula, display_name, molar_mass in SUBSTANCES:
            obj, created = Substance.objects.update_or_create(
                formula=formula,
                defaults={'display_name': display_name, 'molar_mass': molar_mass},
            )
            substance_map[formula] = obj
            status = 'CREATED' if created else 'UPDATED'
            self.stdout.write(f'  [{status}] {formula} ({molar_mass} g/mol)')

        self.stdout.write('\n--- Seeding Problems ---')
        for prob_data in PROBLEMS:
            parts_data = prob_data.pop('parts')

            prob, created = StoichiometryProblem.objects.update_or_create(
                problem_id=prob_data['problem_id'],
                defaults={k: v for k, v in prob_data.items()},
            )
            status = 'CREATED' if created else 'UPDATED'
            self.stdout.write(f'  [{status}] {prob.problem_id}: {prob.title}')

            for order_idx, part_data in enumerate(parts_data):
                given_formula  = part_data.pop('given_formula')
                target_formula = part_data.pop('target_formula')

                ProblemPart.objects.update_or_create(
                    problem=prob,
                    part_label=part_data['part_label'],
                    defaults={
                        **part_data,
                        'given_substance':  substance_map[given_formula],
                        'target_substance': substance_map[target_formula],
                        'order': order_idx,
                    },
                )
                self.stdout.write(
                    f'    Part {part_data["part_label"]}: '
                    f'{given_formula} → {target_formula} '
                    f'({part_data["conversion_type"]})'
                )

            # Restore parts_data so the dict is not mutated for re-runs
            prob_data['parts'] = parts_data

        self.stdout.write(self.style.SUCCESS('\n✓ Seed complete.'))