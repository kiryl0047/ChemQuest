import re

from django import template

register = template.Library()


def _apply_subscript(formula_str):
    """Convert a chemical formula string to HTML with <sub> tags for atom counts.

    Examples:
        "H2O"       -> "H<sub>2</sub>O"
        "CO2"       -> "C<sub>2</sub>O"
        "Fe2O3"     -> "Fe<sub>2</sub>O<sub>3</sub>"
        "H"         -> "H"     (no change if no count)
        "He"        -> "He"    (no change if no count)
        "C6H12O6"   -> "C<sub>6</sub>H<sub>12</sub>O<sub>6</sub>"
    """
    if not formula_str:
        return ""

    result = []
    # Pattern: element symbol (uppercase + optional lowercase) followed by optional digits
    pattern = re.compile(r'([A-Z][a-z]?)(\d*)')

    last_end = 0
    for m in pattern.finditer(formula_str):
        # Append any text before this match
        if m.start() > last_end:
            result.append(formula_str[last_end:m.start()])

        element = m.group(1)
        count = m.group(2)

        # Append element symbol (always plain)
        result.append(element)

        # Append count wrapped in <sub> if there are digits, otherwise nothing
        if count:
            result.append(f'<sub>{count}</sub>')

        last_end = m.end()

    # Append any remaining text after the last match
    if last_end < len(formula_str):
        result.append(formula_str[last_end:])

    return ''.join(result)


@register.filter(name='formula_subscript')
def formula_subscript(formula):
    """Django template filter: convert chemical formula to HTML with subscript counts.

    Usage in templates: {{ formula|formula_subscript }}

    Examples rendered:
        H2O   → H<sub>2</sub>O
        CO2   → C<sub>2</sub>O
        Fe2O3 → Fe<sub>2</sub>O<sub>3</sub>
        H     → H
    """
    return _apply_subscript(formula)