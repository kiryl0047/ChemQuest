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
# Master substance registry (with accurate IUPAC molar masses & periodic layout coords)
# ---------------------------------------------------------------------------
SUBSTANCES = [
    # formula, display_name, molar_mass, is_element, period, group, category
    # --- Period 1 ---
    ('H2',    'Hydrogen Gas',       2.0160,   True,  1, 1,  'reactive_nonmetal'),
    ('He',    'Helium Gas',         4.0026,   True,  1, 18, 'noble_gas'),

    # --- Period 2 ---
    ('Li',    'Lithium metal',      6.9400,   True,  2, 1,  'alkali_metal'),
    ('N2',    'Nitrogen Gas',       28.0134,  True,  2, 15, 'reactive_nonmetal'),
    ('O2',    'Oxygen Gas',         31.9988,  True,  2, 16, 'reactive_nonmetal'),

    # --- Period 3 ---
    ('Na',    'Sodium',             22.9898,  True,  3, 1,  'alkali_metal'),
    ('Mg',    'Magnesium',          24.3050,  True,  3, 2,  'alkaline_earth'),
    ('Al',    'Aluminum',           26.9815,  True,  3, 13, 'post_transition_metal'),
    ('Cl2',   'Chlorine Gas',       70.9060,  True,  3, 17, 'halogen'),

    # --- Period 4 ---
    ('Fe',    'Iron',               55.8450,  True,  4, 8,  'transition_metal'),
    ('Zn',    'Zinc',               65.3800,  True,  4, 12, 'transition_metal'),
    ('Cu',    'Copper',             63.5460,  True,  4, 11, 'transition_metal'),

    # --- Compounds Registry (Assigned as non-elements for sidebar lists) ---
    ('H2O',   'Water',              18.0153,  False, None, None, 'compound'),
    ('SO2',   'Sulfur Dioxide',     64.0638,  False, None, None, 'compound'),
    ('SO3',   'Sulfur Trioxide',    80.0632,  False, None, None, 'compound'),
    ('C3H8',  'Propane',            44.0956,  False, None, None, 'compound'),
    ('CO2',   'Carbon Dioxide',     44.0095,  False, None, None, 'compound'),
    ('AlCl3', 'Aluminum Chloride', 133.3405,  False, None, None, 'compound'),
    ('NH3',   'Ammonia',            17.0305,  False, None, None, 'compound'),
    ('CH4',   'Methane',            16.0425,  False, None, None, 'compound'),
    ('Fe2O3', 'Iron(III) Oxide',   159.6882,  False, None, None, 'compound'),
    ('MgO',   'Magnesium Oxide',    40.3044,  False, None, None, 'compound'),
    ('NaCl',  'Sodium Chloride',    58.4428,  False, None, None, 'compound'),
    ('HCl',   'Hydrochloric Acid',  36.4609,  False, None, None, 'compound'),
    ('ZnCl2', 'Zinc Chloride',     136.2860,  False, None, None, 'compound'),
    ('AgNo3', 'Silver Nitrate',    169.8720,  False, None, None, 'compound'),
    ('AgCl',  'Silver Chloride',   143.3210,  False, None, None, 'compound'),
    ('CuNo3', 'Copper(II) Nitrate',187.5540,  False, None, None, 'compound'),
]

# ---------------------------------------------------------------------------
# Problem seed data
# ---------------------------------------------------------------------------
PROBLEMS = [
    # PROB_101  –  H2 + O2 → H2O
    {
        'problem_id':  'PROB_101',
        'title':       'Hydrogen Combustion',
        'prompt':      'Hydrogen gas reacts with Oxygen gas to produce Water. Given 15.0 g of H2 reacting with excess O2, determine the theoretical yield of water.',
        'reactants_str':       '2:H2,1:O2',
        'products_str':        '2:H2O',
        'correct_coefficients':'2,1,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'How many grams of H2O are produced from 15.0 g of H2?',
                'given_formula':   'H2',
                'given_quantity':  15.0,
                'given_unit':      'g',
                'target_formula':  'H2O',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  134.0424,
            },
        ],
    },

    # PROB_201  –  SO2 + O2 → SO3
    {
        'problem_id':  'PROB_201',
        'title':       'Sulfur Dioxide Oxidation',
        'prompt':      'Sulfur Dioxide reacts with Oxygen gas to form Sulfur Trioxide.',
        'reactants_str':       '2:SO2,1:O2',
        'products_str':        '2:SO3',
        'correct_coefficients':'2,1,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     '(a) If 3.4 mol of SO2 reacts with excess O2, how many moles of SO3 will form?',
                'given_formula':   'SO2',
                'given_quantity':  3.4,
                'given_unit':      'mol',
                'target_formula':  'SO3',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_MOL_TO_MOL,
                'correct_answer':  3.4000,
            },
            {
                'part_label':      'b',
                'part_prompt':     '(b) How many moles of O2 will react completely with 4.7 mol of SO2?',
                'given_formula':   'SO2',
                'given_quantity':  4.7,
                'given_unit':      'mol',
                'target_formula':  'O2',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_MOL_TO_MOL,
                'correct_answer':  2.3500,
            },
        ],
    },

    # PROB_301  –  C3H8 + O2 → CO2 + H2O
    {
        'problem_id':  'PROB_301',
        'title':       'Propane Combustion',
        'prompt':      'Propane reacts with Oxygen gas to form Carbon Dioxide and Water.',
        'reactants_str':       '1:C3H8,5:O2',
        'products_str':        '3:CO2,4:H2O',
        'correct_coefficients':'1,5,3,4',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     '(a) If 2.8 mol of C3H8 reacts with excess O2, how many grams of CO2 will form?',
                'given_formula':   'C3H8',
                'given_quantity':  2.8,
                'given_unit':      'mol',
                'target_formula':  'CO2',
                'target_unit':     'g',
                'conversion_type': CONVERSION_MOL_TO_G,
                'correct_answer':  369.6798,
            },
            {
                'part_label':      'b',
                'part_prompt':     '(b) How many grams of O2 will completely react with 3.8 mol of C3H8?',
                'given_formula':   'C3H8',
                'given_quantity':  3.8,
                'given_unit':      'mol',
                'target_formula':  'O2',
                'target_unit':     'g',
                'conversion_type': CONVERSION_MOL_TO_G,
                'correct_answer':  607.9772,
            },
            {
                'part_label':      'c',
                'part_prompt':     '(c) If 25.0 g of C3H8 reacts with excess O2, how many moles of H2O will form?',
                'given_formula':   'C3H8',
                'given_quantity':  25.0,
                'given_unit':      'g',
                'target_formula':  'H2O',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_G_TO_MOL,
                'correct_answer':  2.2678,
            },
            {
                'part_label':      'd',
                'part_prompt':     '(d) If 38.0 g of H2O are produced, how many moles of CO2 were produced?',
                'given_formula':   'H2O',
                'given_quantity':  38.0,
                'given_unit':      'g',
                'target_formula':  'CO2',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_G_TO_MOL,
                'correct_answer':  1.5820,
            },
        ],
    },

    # PROB_401  –  Al + Cl2 → AlCl3
    {
        'problem_id':  'PROB_401',
        'title':       'Aluminum Chloride Synthesis',
        'prompt':      'Aluminum reacts with Chlorine gas to form Aluminum Chloride.',
        'reactants_str':       '2:Al,3:Cl2',
        'products_str':        '2:AlCl3',
        'correct_coefficients':'2,3,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     '(a) If 35.0 g of Al reacts with excess Cl2, how many grams of AlCl3 will form?',
                'given_formula':   'Al',
                'given_quantity':  35.0,
                'given_unit':      'g',
                'target_formula':  'AlCl3',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  172.9673,
            },
            {
                'part_label':      'b',
                'part_prompt':     '(b) How many grams of Cl2 will react completely with 42.8 g of Al?',
                'given_formula':   'Al',
                'given_quantity':  42.8,
                'given_unit':      'g',
                'target_formula':  'Cl2',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  168.7143,
            },
        ],
    },

    # PROB_102 – N2 + 3 H2 → 2 NH3
    {
        'problem_id':  'PROB_102',
        'title':       'Ammonia Catalyst Synthesis',
        'prompt':      'Nitrogen gas reacts with Hydrogen gas to produce Ammonia (NH3).',
        'reactants_str':       '1:N2,3:H2',
        'products_str':        '2:NH3',
        'correct_coefficients':'1,3,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'How many moles of NH3 are generated from 6.5 moles of N2?',
                'given_formula':   'N2',
                'given_quantity':  6.5,
                'given_unit':      'mol',
                'target_formula':  'NH3',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_MOL_TO_MOL,
                'correct_answer':  13.0000,
            },
            {
                'part_label':      'b',
                'part_prompt':     'How many moles of H2 are required to react with 4.2 moles of N2?',
                'given_formula':   'N2',
                'given_quantity':  4.2,
                'given_unit':      'mol',
                'target_formula':  'H2',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_MOL_TO_MOL,
                'correct_answer':  12.6000,
            }
        ],
    },

    # PROB_103 – CH4 + 2 O2 → CO2 + 2 H2O
    {
        'problem_id':  'PROB_103',
        'title':       'Methane Combustion Chamber',
        'prompt':      'Methane undergoes standard combustion in excess oxygen to yield carbon dioxide and water vapor.',
        'reactants_str':       '1:CH4,2:O2',
        'products_str':        '1:CO2,2:H2O',
        'correct_coefficients':'1,2,1,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'If 12.0 moles of O2 are consumed completely, how many moles of CO2 exit the system?',
                'given_formula':   'O2',
                'given_quantity':  12.0,
                'given_unit':      'mol',
                'target_formula':  'CO2',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_MOL_TO_MOL,
                'correct_answer':  6.0000,
            }
        ],
    },

    # PROB_104 – 4 Fe + 3 O2 → 2 Fe2O3
    {
        'problem_id':  'PROB_104',
        'title':       'Iron Thermal Oxidation',
        'prompt':      'Solid Iron reacts with Atmospheric Oxygen gas to yield Iron(III) Oxide rust flakes.',
        'reactants_str':       '4:Fe,3:O2',
        'products_str':        '2:Fe2O3',
        'correct_coefficients':'4,3,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'How many moles of Fe2O3 form when 0.85 moles of solid Fe oxidize completely?',
                'given_formula':   'Fe',
                'given_quantity':  0.85,
                'given_unit':      'mol',
                'target_formula':  'Fe2O3',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_MOL_TO_MOL,
                'correct_answer':  0.4250,
            }
        ],
    },

    # PROB_105 – 2 Mg + O2 → 2 MgO
    {
        'problem_id':  'PROB_105',
        'title':       'Magnesium Flash Ribbons',
        'prompt':      'Magnesium ribbon strips ignite intensely inside oxygen chambers to form fine Magnesium Oxide powders.',
        'reactants_str':       '2:Mg,1:O2',
        'products_str':        '2:MgO',
        'correct_coefficients':'2,1,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'Find the mole yield of MgO created from the combustion of 14.5 moles of pure Mg.',
                'given_formula':   'Mg',
                'given_quantity':  14.5,
                'given_unit':      'mol',
                'target_formula':  'MgO',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_MOL_TO_MOL,
                'correct_answer':  14.5000,
            }
        ],
    },

    # PROB_202 – Mole-to-Gram Ammonia Extraction
    {
        'problem_id':  'PROB_202',
        'title':       'Ammonia Cryo-Extraction',
        'prompt':      'Nitrogen gas reacts with Hydrogen gas to produce Ammonia (NH3).',
        'reactants_str':       '1:N2,3:H2',
        'products_str':        '2:NH3',
        'correct_coefficients':'1,3,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'Calculate the mass in grams of NH3 yielded from 3.5 moles of N2 gas.',
                'given_formula':   'N2',
                'given_quantity':  3.5,
                'given_unit':      'mol',
                'target_formula':  'NH3',
                'target_unit':     'g',
                'conversion_type': CONVERSION_MOL_TO_G,
                'correct_answer':  119.2135,
            }
        ],
    },

    # PROB_203 – Mole-to-Gram Rust Conversion
    {
        'problem_id':  'PROB_203',
        'title':       'Structural Mass Expansion',
        'prompt':      'Solid Iron reacts with Atmospheric Oxygen gas to yield Iron(III) Oxide rust flakes.',
        'reactants_str':       '4:Fe,3:O2',
        'products_str':        '2:Fe2O3',
        'correct_coefficients':'4,3,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'Calculate the output mass of Fe2O3 in grams from 5.2 moles of completely oxidized Fe.',
                'given_formula':   'Fe',
                'given_quantity':  5.2,
                'given_unit':      'mol',
                'target_formula':  'Fe2O3',
                'target_unit':     'g',
                'conversion_type': CONVERSION_MOL_TO_G,
                'correct_answer':  415.1893,
            }
        ],
    },

    # PROB_204 – Mole-to-Gram Methane Exhaust
    {
        'problem_id':  'PROB_204',
        'title':       'Hydrocarbon Displacement Exhaust',
        'prompt':      'Methane undergoes standard combustion in excess oxygen to yield carbon dioxide and water vapor.',
        'reactants_str':       '1:CH4,2:O2',
        'products_str':        '1:CO2,2:H2O',
        'correct_coefficients':'1,2,1,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'Determine the total grams of CO2 gas emitted from the breakdown of 0.75 moles of CH4 fuel.',
                'given_formula':   'CH4',
                'given_quantity':  0.75,
                'given_unit':      'mol',
                'target_formula':  'CO2',
                'target_unit':     'g',
                'conversion_type': CONVERSION_MOL_TO_G,
                'correct_answer':  33.0071,
            }
        ],
    },

    # PROB_205 – 2 Na + Cl2 → 2 NaCl
    {
        'problem_id':  'PROB_205',
        'title':       'Halide Condensation Matrices',
        'prompt':      'Pure elemental Sodium metal reacts dynamically when placed in Chlorine gas chambers to deposit crystalline Sodium Chloride.',
        'reactants_str':       '2:Na,1:Cl2',
        'products_str':        '2:NaCl',
        'correct_coefficients':'2,1,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'How many grams of NaCl crystal deposit form if 1.45 moles of Cl2 gas execute full conversion bounds?',
                'given_formula':   'Cl2',
                'given_quantity':  1.45,
                'given_unit':      'mol',
                'target_formula':  'NaCl',
                'target_unit':     'g',
                'conversion_type': CONVERSION_MOL_TO_G,
                'correct_answer':  169.4841,
            }
        ],
    },

    # PROB_302 – Gram-to-Mole Water Electrolysis
    {
        'problem_id':  'PROB_302',
        'title':       'Hydro-Fuel Inverse Analytics',
        'prompt':      'Hydrogen gas reacts with Oxygen gas to produce Water.',
        'reactants_str':       '2:H2,1:O2',
        'products_str':        '2:H2O',
        'correct_coefficients':'2,1,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'If a combustion reaction vessel isolates 75.0 grams of output H2O, how many moles of input H2 were burned?',
                'given_formula':   'H2O',
                'given_quantity':  75.0,
                'given_unit':      'g',
                'target_formula':  'H2',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_G_TO_MOL,
                'correct_answer':  4.1631,
            }
        ],
    },

    # PROB_303 – Zn + 2 HCl → ZnCl2 + H2
    {
        'problem_id':  'PROB_303',
        'title':       'Acidic Metal Single-Replacement',
        'prompt':      'Solid Zinc metal dissolves inside aqueous Hydrochloric Acid conduits, releasing Hydrogen displacement bubbles and clear Zinc Chloride.',
        'reactants_str':       '1:Zn,2:HCl',
        'products_str':        '1:ZnCl2,1:H2',
        'correct_coefficients':'1,2,1,1',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'If 45.0 grams of HCl are completely consumed by active zinc sheets, calculate the moles of escaping H2 gas.',
                'given_formula':   'HCl',
                'given_quantity':  45.0,
                'given_unit':      'g',
                'target_formula':  'H2',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_G_TO_MOL,
                'correct_answer':  0.6171,
            }
        ],
    },

    # PROB_304 – Cu + 2 AgNO3 → 2 Ag + Cu(NO3)2
    {
        'problem_id':  'PROB_304',
        'title':       'Silver Nitrate Displacement',
        'prompt':      'Solid copper wires submerge inside Silver Nitrate solutions, creating a crystalline silver plating and deep blue copper nitrate.',
        'reactants_str':       '1:Cu,2:AgNo3',
        'products_str':        '2:Ag,1:CuNo3',
        'correct_coefficients':'1,2,2,1',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'How many moles of liquid CuNo3 byproducts build up if 12.5 grams of pure metallic copper execute complete oxidation?',
                'given_formula':   'Cu',
                'given_quantity':  12.5,
                'given_unit':      'g',
                'target_formula':  'CuNo3',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_G_TO_MOL,
                'correct_answer':  0.1967,
            }
        ],
    },

    # PROB_305 – Gram-to-Mole Magnesium Flare Core
    {
        'problem_id':  'PROB_305',
        'title':       'Incineration Vault Analytics',
        'prompt':      'Magnesium ribbon strips ignite intensely inside oxygen chambers to form fine Magnesium Oxide powders.',
        'reactants_str':       '2:Mg,1:O2',
        'products_str':        '2:MgO',
        'correct_coefficients':'2,1,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'A spent signaling flare contains 120.0 grams of white MgO residue ash. How many moles of O2 gas were bound into the flare casing during combustion?',
                'given_formula':   'MgO',
                'given_quantity':  120.0,
                'given_unit':      'g',
                'target_formula':  'O2',
                'target_unit':     'mol',
                'conversion_type': CONVERSION_G_TO_MOL,
                'correct_answer':  1.4887,
            }
        ],
    },

    # PROB_402 – Gram-to-Gram Haber Optimization
    {
        'problem_id':  'PROB_402',
        'title':       'Haber Process Mass Optimizers',
        'prompt':      'Nitrogen gas reacts with Hydrogen gas to produce Ammonia (NH3).',
        'reactants_str':       '1:N2,3:H2',
        'products_str':        '2:NH3',
        'correct_coefficients':'1,3,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'If structural pipes pump 500.0 grams of H2 gas into a heated synthesis catalyst grid, calculate the output yield of NH3 in grams.',
                'given_formula':   'H2',
                'given_quantity':  500.0,
                'given_unit':      'g',
                'target_formula':  'NH3',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  2815.5754,
            }
        ],
    },

    # PROB_403 – Gram-to-Gram Methane Fuel Scrubbers
    {
        'problem_id':  'PROB_403',
        'title':       'Aliphatic Combustion Residues',
        'prompt':      'Methane undergoes standard combustion in excess oxygen to yield carbon dioxide and water vapor.',
        'reactants_str':       '1:CH4,2:O2',
        'products_str':        '1:CO2,2:H2O',
        'correct_coefficients':'1,2,1,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'An engine burns 85.0 grams of CH4 fuel matrix. Find the exact mass in grams of escaping H2O condensation generated.',
                'given_formula':   'CH4',
                'given_quantity':  85.0,
                'given_unit':      'g',
                'target_formula':  'H2O',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  191.1340,
            }
        ],
    },

    # PROB_404 – Gram-to-Gram Acidic Gas Condensers
    {
        'problem_id':  'PROB_404',
        'title':       'Sulfur Trioxide Volcanic Yield',
        'prompt':      'Sulfur Dioxide reacts with Oxygen gas to form Sulfur Trioxide.',
        'reactants_str':       '2:SO2,1:O2',
        'products_str':        '2:SO3',
        'correct_coefficients':'2,1,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'How many grams of atmospheric SO3 gas are synthesized when volcanic smoke vents inject 240.0 grams of raw SO2 into clouds containing excess O2?',
                'given_formula':   'SO2',
                'given_quantity':  240.0,
                'given_unit':      'g',
                'target_formula':  'SO3',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  299.9322,
            }
        ],
    },

    # PROB_405 – Gram-to-Gram Blast Furnace Shavings
    {
        'problem_id':  'PROB_405',
        'title':       'Iron Smelting Calcination Scaling',
        'prompt':      'Solid Iron reacts with Atmospheric Oxygen gas to yield Iron(III) Oxide rust flakes.',
        'reactants_str':       '4:Fe,3:O2',
        'products_str':        '2:Fe2O3',
        'correct_coefficients':'4,3,2',
        'is_limiting_problem': False,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'A steel structural beam drops 650.0 grams of fine metallic Fe dust shavings onto a processing floor. What is the final weight of Fe2O3 scale powder generated after full thermal corrosion finishes?',
                'given_formula':   'Fe',
                'given_quantity':  650.0,
                'given_unit':      'g',
                'target_formula':  'Fe2O3',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  929.1417,
            }
        ],
    },

    # -----------------------------------------------------------------------
    # MULTI-MODULE CAPSTONE CHALLENGES (is_limiting_problem = True)
    # -----------------------------------------------------------------------

    # PROB_501 – Al + Cl2 → AlCl3 (Existing Capstone)
    {
        'problem_id':  'PROB_501',
        'title':       'Chamber Synthesis Boundary',
        'prompt':      'Solid Aluminum reacts with Chlorine gas to form Aluminum Chloride. If 35.0 g of Al are mixed with 45.0 g of Cl2 inside a sealed reactor chamber, evaluate both structural reaction tracks side-by-side to find the limiting factor.',
        'reactants_str':       '2:Al,3:Cl2',
        'products_str':        '2:AlCl3',
        'correct_coefficients':'2,3,2',
        'is_limiting_problem': True,  
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'Track A (Al): Calculate the theoretical mass of AlCl3 produced if Aluminum is completely consumed.',
                'given_formula':   'Al',
                'given_quantity':  35.0,
                'given_unit':      'g',
                'target_formula':  'AlCl3',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  172.9673,
            },
            {
                'part_label':      'b',
                'part_prompt':     'Track B (Cl2): Calculate the theoretical mass of AlCl3 produced if Chlorine gas is completely consumed.',
                'given_formula':   'Cl2',
                'given_quantity':  45.0,
                'given_unit':      'g',
                'target_formula':  'AlCl3',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  56.4154,
            },
            {
                'part_label':      'c',
                'part_prompt':     'Excess Analytics: Use the limiting mass (45.0 g Cl2) to calculate exactly how many grams of Aluminum were consumed.',
                'given_formula':   'Cl2',
                'given_quantity':  45.0,
                'given_unit':      'g',
                'target_formula':  'Al',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  11.4116,
            },
        ],
    },

    # PROB_502 – Haber Process Capstone Challenge
    {
        'problem_id':  'PROB_502',
        'title':       'Haber Catalyst Core Starvation',
        'prompt':      'An industrial synthesis grid combines 80.0 grams of Nitrogen gas with 20.0 grams of Hydrogen gas to produce Ammonia. Chart both raw element tracks to pinpoint the true yield limit.',
        'reactants_str':       '1:N2,3:H2',
        'products_str':        '2:NH3',
        'correct_coefficients':'1,3,2',
        'is_limiting_problem': True,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'Track A (N2): Compute total grams of NH3 formed if all Nitrogen gas converts fully.',
                'given_formula':   'N2',
                'given_quantity':  80.0,
                'given_unit':      'g',
                'target_formula':  'NH3',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  97.2781,
            },
            {
                'part_label':      'b',
                'part_prompt':     'Track B (H2): Compute total grams of NH3 formed if all Hydrogen gas converts fully.',
                'given_formula':   'H2',
                'given_quantity':  20.0,
                'given_unit':      'g',
                'target_formula':  'NH3',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  112.6230,
            },
            {
                'part_label':      'c',
                'part_prompt':     'Excess Analytics: Using the true limiting reagent mass (80.0 g N2), calculate exactly how many grams of H2 gas were used.',
                'given_formula':   'N2',
                'given_quantity':  80.0,
                'given_unit':      'g',
                'target_formula':  'H2',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  17.2703,
            }
        ],
    },

    # PROB_503 – Rocket Combustion Matrix (2 H2 + O2 → 2 H2O)
    {
        'problem_id':  'PROB_503',
        'title':       'Cryogenic Oxidizer Volumetric Check',
        'prompt':      'Cryogenic engine manifolds mix 40.0 grams of Hydrogen gas with 150.0 grams of Oxygen gas to produce water exhaust vapor. Evaluate the payload capacity constraint.',
        'reactants_str':       '2:H2,1:O2',
        'products_str':        '2:H2O',
        'correct_coefficients':'2,1,2',
        'is_limiting_problem': True,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'Track A (H2): Determine grams of H2O water condensation generated if H2 is the limit factor.',
                'given_formula':   'H2',
                'given_quantity':  40.0,
                'given_unit':      'g',
                'target_formula':  'H2O',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  357.4464,
            },
            {
                'part_label':      'b',
                'part_prompt':     'Track B (O2): Determine grams of H2O water condensation generated if O2 is the limit factor.',
                'given_formula':   'O2',
                'given_quantity':  150.0,
                'given_unit':      'g',
                'target_formula':  'H2O',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  168.9001,
            },
            {
                'part_label':      'c',
                'part_prompt':     'Excess Analytics: Calculate how many grams of liquid H2 fuel were actually consumed based on the limiting Oxygen volume.',
                'given_formula':   'O2',
                'given_quantity':  150.0,
                'given_unit':      'g',
                'target_formula':  'H2',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  18.9004,
            }
        ],
    },

    # PROB_504 – Methane Combustion Capstone
    {
        'problem_id':  'PROB_504',
        'title':       'Sub-Atmospheric Burn Ceiling',
        'prompt':      'An environmental glove box locks 60.0 grams of pure Methane gas inside a chamber filled with 130.0 grams of Oxygen gas. Trigger dual track computations to identify exhaust parameters.',
        'reactants_str':       '1:CH4,2:O2',
        'products_str':        '1:CO2,2:H2O',
        'correct_coefficients':'1,2,1,2',
        'is_limiting_problem': True,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'Track A (CH4): Solve for total grams of generated CO2 gas assuming the alkane fuel is exhausted completely.',
                'given_formula':   'CH4',
                'given_quantity':  60.0,
                'given_unit':      'g',
                'target_formula':  'CO2',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  164.5951,
            },
            {
                'part_label':      'b',
                'part_prompt':     'Track B (O2): Solve for total grams of generated CO2 gas assuming the oxygen supply completely starves out.',
                'given_formula':   'O2',
                'given_quantity':  130.0,
                'given_unit':      'g',
                'target_formula':  'CO2',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  89.3951,
            },
            {
                'part_label':      'c',
                'part_prompt':     'Excess Analytics: Find the weight in grams of Methane broken down using the limiting weight parameter.',
                'given_formula':   'O2',
                'given_quantity':  130.0,
                'given_unit':      'g',
                'target_formula':  'CH4',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  32.5855,
            }
        ],
    },

    # PROB_505 – Magnesium Powder Smelting Capstone
    {
        'problem_id':  'PROB_505',
        'title':       'Magnesium Smelting Boundary',
        'prompt':      'A metal forging cell blends 50.0 grams of raw solid Magnesium particles with 40.0 grams of Oxygen gas to form Magnesium Oxide powder. Evaluate the chemical matrix limitations.',
        'reactants_str':       '2:Mg,1:O2',
        'products_str':        '2:MgO',
        'correct_coefficients':'2,1,2',
        'is_limiting_problem': True,
        'parts': [
            {
                'part_label':      'a',
                'part_prompt':     'Track A (Mg): Solve for total grams of solid MgO ash created if the magnesium blocks oxidize completely.',
                'given_formula':   'Mg',
                'given_quantity':  50.0,
                'given_unit':      'g',
                'target_formula':  'MgO',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  82.9138,
            },
            {
                'part_label':      'b',
                'part_prompt':     'Track B (O2): Solve for total grams of solid MgO ash created if the oxygen gas reserves run out first.',
                'given_formula':   'O2',
                'given_quantity':  40.0,
                'given_unit':      'g',
                'target_formula':  'MgO',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  100.7648,
            },
            {
                'part_label':      'c',
                'part_prompt':     'Excess Analytics: Calculate the exact mass in grams of Oxygen gas gas bound into the ash pile based on the limiting factor.',
                'given_formula':   'Mg',
                'given_quantity':  50.0,
                'given_unit':      'g',
                'target_formula':  'O2',
                'target_unit':     'g',
                'conversion_type': CONVERSION_G_TO_G,
                'correct_answer':  32.9138,
            }
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed the database with all ChemQuest sample problems and substances.'

    def handle(self, *args, **options):
        self.stdout.write('--- Seeding Substances ---')
        substance_map = {}
        for record in SUBSTANCES:
            formula      = record[0]
            display_name = record[1]
            molar_mass   = record[2]
            
            # Extract metadata elements cleanly to update the target attributes
            is_element   = record[3]
            period       = record[4]
            group        = record[5]
            category     = record[6]

            obj, created = Substance.objects.update_or_create(
                formula=formula,
                defaults={
                    'display_name': display_name, 
                    'molar_mass': molar_mass,
                    'is_element': is_element,
                    'period': period,
                    'group': group,
                    'category': category
                },
            )
            substance_map[formula] = obj
            status = 'CREATED' if created else 'UPDATED'
            self.stdout.write(f'  [{status}] {formula} ({molar_mass} g/mol) Grid Space: ({period}, {group})')

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
                limiting_qtys  = part_data.pop('limiting_given_quantities', {})

                ProblemPart.objects.update_or_create(
                    problem=prob,
                    part_label=part_data['part_label'],
                    defaults={
                        **part_data,
                        'given_substance':  substance_map[given_formula],
                        'target_substance': substance_map[target_formula],
                        'order':            order_idx,
                        'is_limiting_part': part_data.get('is_limiting_part', False) or bool(limiting_qtys),
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