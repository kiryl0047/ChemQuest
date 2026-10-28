"""On-demand stoichiometry problem generation for the Synthesis Challenge.

The Synthesis Challenge never reuses the seeded catalog verbatim: every attempt
is built from a fresh batch of generated problems. Generation stays inside the
validated chemistry domain by recombining the balanced reactions already known
to the app while randomising the given substance, the target substance, the
quantity and the conversion type.

Generated problems are flagged with ``is_generated=True`` so they are excluded
from the Problem Lobby, dashboards and completion counts.
"""

import random
import uuid

from .models import (
    Substance, StoichiometryProblem, ProblemPart,
    CONVERSION_MOL_TO_MOL, CONVERSION_MOL_TO_G,
    CONVERSION_G_TO_MOL, CONVERSION_G_TO_G,
)

# ---------------------------------------------------------------------------
# Balanced reaction library (formula, coefficient). Every formula already
# exists in the Substance registry with an accurate IUPAC molar mass.
# ---------------------------------------------------------------------------
REACTIONS = [
    {
        'title': 'Hydrogen Combustion',
        'prompt': 'Hydrogen gas reacts with Oxygen gas to produce Water.',
        'reactants': [('H2', 2), ('O2', 1)],
        'products':  [('H2O', 2)],
    },
    {
        'title': 'Ammonia Catalyst Synthesis',
        'prompt': 'Nitrogen gas reacts with Hydrogen gas to produce Ammonia (NH3).',
        'reactants': [('N2', 1), ('H2', 3)],
        'products':  [('NH3', 2)],
    },
    {
        'title': 'Methane Combustion',
        'prompt': 'Methane undergoes standard combustion in excess oxygen to yield carbon dioxide and water vapor.',
        'reactants': [('CH4', 1), ('O2', 2)],
        'products':  [('CO2', 1), ('H2O', 2)],
    },
    {
        'title': 'Iron Thermal Oxidation',
        'prompt': 'Solid Iron reacts with Atmospheric Oxygen gas to yield Iron(III) Oxide rust flakes.',
        'reactants': [('Fe', 4), ('O2', 3)],
        'products':  [('Fe2O3', 2)],
    },
    {
        'title': 'Magnesium Flash Ribbons',
        'prompt': 'Magnesium ribbon strips ignite intensely inside oxygen chambers to form fine Magnesium Oxide powders.',
        'reactants': [('Mg', 2), ('O2', 1)],
        'products':  [('MgO', 2)],
    },
    {
        'title': 'Aluminum Chloride Synthesis',
        'prompt': 'Aluminum reacts with Chlorine gas to form Aluminum Chloride.',
        'reactants': [('Al', 2), ('Cl2', 3)],
        'products':  [('AlCl3', 2)],
    },
    {
        'title': 'Propane Combustion',
        'prompt': 'Propane reacts with Oxygen gas to form Carbon Dioxide and Water.',
        'reactants': [('C3H8', 1), ('O2', 5)],
        'products':  [('CO2', 3), ('H2O', 4)],
    },
    {
        'title': 'Sulfur Dioxide Oxidation',
        'prompt': 'Sulfur Dioxide reacts with Oxygen gas to form Sulfur Trioxide.',
        'reactants': [('SO2', 2), ('O2', 1)],
        'products':  [('SO3', 2)],
    },
    {
        'title': 'Acidic Metal Single-Replacement',
        'prompt': 'Solid Zinc metal dissolves inside aqueous Hydrochloric Acid conduits, releasing Hydrogen displacement bubbles and clear Zinc Chloride.',
        'reactants': [('Zn', 1), ('HCl', 2)],
        'products':  [('ZnCl2', 1), ('H2', 1)],
    },
    {
        'title': 'Silver Nitrate Displacement',
        'prompt': 'Solid copper wires submerge inside Silver Nitrate solutions, creating crystalline silver plating and deep blue copper nitrate.',
        'reactants': [('Cu', 1), ('AgNo3', 2)],
        'products':  [('Ag', 2), ('CuNo3', 1)],
    },
    {
        'title': 'Halide Condensation Matrices',
        'prompt': 'Pure elemental Sodium metal reacts dynamically when placed in Chlorine gas chambers to deposit crystalline Sodium Chloride.',
        'reactants': [('Na', 2), ('Cl2', 1)],
        'products':  [('NaCl', 2)],
    },
]

# conversion_type -> (given_unit, target_unit)
TYPE_UNITS = {
    CONVERSION_MOL_TO_MOL: ('mol', 'mol'),
    CONVERSION_MOL_TO_G:   ('mol', 'g'),
    CONVERSION_G_TO_MOL:   ('g', 'mol'),
    CONVERSION_G_TO_G:     ('g', 'g'),
}

GENERATED_PREFIX = 'SYN_'


def _serialise_side(entries):
    return ','.join(f'{coeff}:{formula}' for formula, coeff in entries)


def _available_reactions():
    """Only recombine reactions whose substances exist in this database."""
    known = set(Substance.objects.values_list('formula', flat=True))
    available = []
    for reaction in REACTIONS:
        needed = {f for f, _ in reaction['reactants'] + reaction['products']}
        if needed <= known:
            available.append(reaction)
    if not available:
        raise RuntimeError('No generatable reaction: substance registry is incomplete.')
    return available


def _random_quantity(unit, rng):
    """Coursework-friendly magnitudes: grams are larger than mole counts."""
    if unit == 'g':
        return round(rng.uniform(5.0, 250.0), 1)
    return round(rng.uniform(0.5, 12.0), 2)


def _compute_answer(quantity, given_unit, target_unit,
                    mm_given, mm_target, coeff_given, coeff_target):
    moles_given = quantity / mm_given if given_unit == 'g' else quantity
    moles_target = moles_given * coeff_target / coeff_given
    return moles_target * mm_target if target_unit == 'g' else moles_target


def generate_synthesis_part(conversion_type=None, rng=None):
    """Create and persist one fresh problem/part pair and return the part row.

    ``conversion_type`` lets the caller target the user's weakest skill; when
    omitted a random conversion type is used.
    """
    rng = rng or random
    reaction = rng.choice(_available_reactions())

    sides = reaction['reactants'] + reaction['products']
    given_formula, given_coeff = rng.choice(sides)
    target_candidates = [(f, c) for f, c in sides if f != given_formula]
    target_formula, target_coeff = rng.choice(target_candidates)

    ct = conversion_type or rng.choice(list(TYPE_UNITS))
    given_unit, target_unit = TYPE_UNITS[ct]

    substances = {
        s.formula: s
        for s in Substance.objects.filter(
            formula__in=[given_formula, target_formula])
    }
    given_substance = substances[given_formula]
    target_substance = substances[target_formula]

    quantity = _random_quantity(given_unit, rng)
    answer = _compute_answer(
        quantity, given_unit, target_unit,
        float(given_substance.molar_mass), float(target_substance.molar_mass),
        given_coeff, target_coeff,
    )
    # Resample a few times so generated yields stay coursework-realistic
    # (avoids answers like 2 300 g dribbling out of a 5 g sample).
    for _ in range(8):
        if 0.1 <= answer <= 1500:
            break
        quantity = _random_quantity(given_unit, rng)
        answer = _compute_answer(
            quantity, given_unit, target_unit,
            float(given_substance.molar_mass), float(target_substance.molar_mass),
            given_coeff, target_coeff,
        )

    problem = StoichiometryProblem.objects.create(
        problem_id=f'{GENERATED_PREFIX}{uuid.uuid4().hex[:10].upper()}',
        title=reaction['title'],
        prompt=reaction['prompt'],
        reactants_str=_serialise_side(reaction['reactants']),
        products_str=_serialise_side(reaction['products']),
        correct_coefficients=','.join(
            str(c) for _, c in reaction['reactants'] + reaction['products']),
        is_generated=True,
    )

    return ProblemPart.objects.create(
        problem=problem,
        part_label='a',
        part_prompt=(
            f'Convert {quantity:g} {given_unit} of {given_formula} '
            f'into {target_unit} of {target_formula}.'
        ),
        given_substance=given_substance,
        given_quantity=quantity,
        given_unit=given_unit,
        target_substance=target_substance,
        target_unit=target_unit,
        conversion_type=ct,
        correct_answer=round(answer, 4),
    )


def prune_generated_problems(keep=300):
    """Keep the generated pool bounded; older attempts are no longer gradeable."""
    stale_ids = list(
        StoichiometryProblem.objects
        .filter(is_generated=True)
        .order_by('-pk')
        .values_list('pk', flat=True)[keep:]
    )
    if stale_ids:
        StoichiometryProblem.objects.filter(pk__in=stale_ids).delete()
