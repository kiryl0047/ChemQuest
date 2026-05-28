from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# ─────────────────────────────────────────────
#  XP / LEVEL FORMULA (single source of truth)
#  Level  = (total_xp // 100) + 1
#  Progress % toward next level = (total_xp % 100)
# ─────────────────────────────────────────────
XP_PER_LEVEL = 100
MODULE2_NODE_XP = 15      # Per verified node in Step-Grid Workspace
MODULE3_COMPLETE_XP = 50  # Limiting reagent final validation bonus


class UserProfile(models.Model):
    """
    One-to-one extension of Django's built-in User model.
    Stores cumulative XP and derives Level + progress dynamically
    via properties — no redundant stored columns that can drift.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    total_xp = models.PositiveIntegerField(default=0)

    # ── Derived Properties ────────────────────────────────────────
    @property
    def level(self) -> int:
        """Returns current level based on XP threshold formula."""
        return (self.total_xp // XP_PER_LEVEL) + 1

    @property
    def xp_into_current_level(self) -> int:
        """XP accumulated since the start of the current level."""
        return self.total_xp % XP_PER_LEVEL

    @property
    def level_progress_pct(self) -> int:
        """Integer percentage (0–99) toward the next level threshold."""
        return self.xp_into_current_level  # xp_per_level == 100, so 1 XP == 1 %

    # ── XP Grant Helper ───────────────────────────────────────────
    def award_xp(self, amount: int) -> dict:
        """
        Atomically adds XP and returns a summary dict for the
        JSON response pipeline. Returns level-up flag so the
        front-end can trigger a level-up animation.
        """
        level_before = self.level
        self.total_xp += amount
        self.save(update_fields=['total_xp'])
        level_after = self.level

        return {
            'xp_awarded': amount,
            'total_xp': self.total_xp,
            'level': level_after,
            'leveled_up': level_after > level_before,
            'level_progress_pct': self.level_progress_pct,
        }

    def __str__(self):
        return f"{self.user.username} — LVL {self.level} ({self.total_xp} XP)"


# ── Auto-create a UserProfile whenever a new User is saved ────────
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # Guard: migrate-safe in case the profile doesn't exist yet
    UserProfile.objects.get_or_create(user=instance)


# ─────────────────────────────────────────────
#  Existing models — unchanged
# ─────────────────────────────────────────────
class StoichiometryProblem(models.Model):
    problem_id = models.CharField(max_length=50, unique=True)
    prompt = models.TextField()
    correct_coefficients = models.CharField(max_length=20)
    reactant_a_mass = models.DecimalField(max_digits=10, decimal_places=4)
    product_mass = models.DecimalField(max_digits=10, decimal_places=4)

    def __str__(self):
        return self.problem_id


class StudentTelemetryLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    problem_id = models.CharField(max_length=50)
    module_phase = models.IntegerField(default=1)
    is_correct = models.BooleanField(default=False)
    attempts_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Telemetry-{self.problem_id}"

# ---------------------------------------------------------------------------
# Conversion type constants
# ---------------------------------------------------------------------------
CONVERSION_MOL_TO_MOL = 'mol_to_mol'
CONVERSION_MOL_TO_G   = 'mol_to_g'
CONVERSION_G_TO_MOL   = 'g_to_mol'
CONVERSION_G_TO_G     = 'g_to_g'

CONVERSION_CHOICES = [
    (CONVERSION_MOL_TO_MOL, 'mol A → mol B  (1 node)'),
    (CONVERSION_MOL_TO_G,   'mol A → g B    (2 nodes)'),
    (CONVERSION_G_TO_MOL,   'g A  → mol B   (2 nodes)'),
    (CONVERSION_G_TO_G,     'g A  → g B     (3 nodes)'),
]

# Node counts required for each conversion type
NODE_COUNT = {
    CONVERSION_MOL_TO_MOL: 1,
    CONVERSION_MOL_TO_G:   2,
    CONVERSION_G_TO_MOL:   2,
    CONVERSION_G_TO_G:     3,
}


# ---------------------------------------------------------------------------
# Chemical substance registry  (H2, O2, SO2, C3H8 …)
# ---------------------------------------------------------------------------
class Substance(models.Model):
    formula      = models.CharField(max_length=30, unique=True)   # e.g. "SO2"
    display_name = models.CharField(max_length=80)                # e.g. "Sulfur Dioxide"
    molar_mass   = models.DecimalField(max_digits=10, decimal_places=4)  # g/mol

    def __str__(self):
        return f"{self.formula} ({self.molar_mass} g/mol)"


# ---------------------------------------------------------------------------
# Top-level reaction problem  (one balanced equation, N sub-parts)
# ---------------------------------------------------------------------------
class StoichiometryProblem(models.Model):
    problem_id   = models.CharField(max_length=50, unique=True)
    title        = models.CharField(max_length=200)               # short label
    prompt       = models.TextField()                             # full word-problem text

    # Balanced equation stored as  "coeff:formula,..."  for reactants | products
    # Example:  reactants="2:H2,1:O2"   products="2:H2O"
    reactants_str = models.CharField(max_length=200)
    products_str  = models.CharField(max_length=200)

    # Comma-separated expected coefficients in reactant→product order
    # e.g. "2,1,2"  means r0=2, r1=1, p0=2
    correct_coefficients = models.CharField(max_length=50)

    is_limiting_problem = models.BooleanField(default=False)

    def __str__(self):
        return f"[{self.problem_id}] {self.title}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def parse_side(self, side_str):
        """
        Parse "2:H2,1:O2" → [{'coeff': 2, 'formula': 'H2'}, ...]
        """
        result = []
        for token in side_str.split(','):
            coeff_str, formula = token.strip().split(':')
            result.append({'coeff': int(coeff_str), 'formula': formula.strip()})
        return result

    @property
    def reactants(self):
        return self.parse_side(self.reactants_str)

    @property
    def products(self):
        return self.parse_side(self.products_str)


# ---------------------------------------------------------------------------
# Sub-question / part  (each row in the problem set, e.g. part a, b, c, d)
# ---------------------------------------------------------------------------
class ProblemPart(models.Model):
    problem      = models.ForeignKey(StoichiometryProblem, on_delete=models.CASCADE,
                                     related_name='parts')
    part_label   = models.CharField(max_length=5)    # "a", "b", "c", "d"
    part_prompt  = models.TextField()                # "If 3.4 moles of SO2…"

    # What the student starts with
    given_substance  = models.ForeignKey(Substance, on_delete=models.PROTECT,
                                         related_name='given_parts')
    given_quantity   = models.DecimalField(max_digits=12, decimal_places=4)
    given_unit       = models.CharField(max_length=10, default='g')   # 'g' or 'mol'

    # What the student must find
    target_substance = models.ForeignKey(Substance, on_delete=models.PROTECT,
                                         related_name='target_parts')
    target_unit      = models.CharField(max_length=10, default='g')   # 'g' or 'mol'

    conversion_type  = models.CharField(max_length=20, choices=CONVERSION_CHOICES,
                                        default=CONVERSION_G_TO_G)

    # Correct answer (pre-computed, stored for fast validation)
    correct_answer   = models.DecimalField(max_digits=14, decimal_places=4)

    # For limiting reagent problems: flag this part as the limiting analysis part
    is_limiting_part = models.BooleanField(default=False)

    # For limiting-reagent parts: per-reactant starting quantities
    # e.g. {"Al": 35.0, "Cl2": 45.0}
    limiting_given_quantities = models.JSONField(default=dict, blank=True)

    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order']
        unique_together = [('problem', 'part_label')]

    def __str__(self):
        return f"{self.problem.problem_id} Part {self.part_label}"

    @property
    def node_count(self):
        return NODE_COUNT[self.conversion_type]

    # ------------------------------------------------------------------
    # Build the ordered list of expected fraction cards for this part.
    # Each dict drives one fraction-node in the template.
    # ------------------------------------------------------------------
    def expected_nodes(self):
        """
        Returns an ordered list of dicts, one per conversion step:
            {
                'num_value':  float,
                'num_unit':   str,       # token understood by JS unit-selector
                'den_value':  float,
                'den_unit':   str,
            }

        Conversion step rules
        ─────────────────────
        g_to_g  (3 nodes):
            Node 1: given_g → mol_given     (1 mol A / molar_mass_A g A)
            Node 2: mol_given → mol_target  (coeff_B mol B / coeff_A mol A)
            Node 3: mol_target → g_target   (molar_mass_B g B / 1 mol B)

        mol_to_g  (2 nodes):
            Node 1: mol_given → mol_target  (coeff_B / coeff_A)
            Node 2: mol_target → g_target   (molar_mass_B / 1)

        g_to_mol  (2 nodes):
            Node 1: g_given → mol_given     (1 / molar_mass_A)
            Node 2: mol_given → mol_target  (coeff_B / coeff_A)

        mol_to_mol  (1 node):
            Node 1: mol_given → mol_target  (coeff_B / coeff_A)
        """
        problem = self.problem
        gf = self.given_substance.formula
        tf = self.target_substance.formula
        mm_given  = float(self.given_substance.molar_mass)
        mm_target = float(self.target_substance.molar_mass)

        # Retrieve stoichiometric coefficients from the balanced equation
        coeff_given  = _get_coeff(problem, gf)
        coeff_target = _get_coeff(problem, tf)

        ct = self.conversion_type
        nodes = []

        if ct == CONVERSION_G_TO_G:
            nodes = [
                _node(1,          f'mol_{gf}',  mm_given,  f'g_{gf}'),
                _node(coeff_target, f'mol_{tf}', coeff_given, f'mol_{gf}'),
                _node(mm_target,  f'g_{tf}',    1,         f'mol_{tf}'),
            ]
        elif ct == CONVERSION_MOL_TO_G:
            nodes = [
                _node(coeff_target, f'mol_{tf}', coeff_given, f'mol_{gf}'),
                _node(mm_target,  f'g_{tf}',    1,         f'mol_{tf}'),
            ]
        elif ct == CONVERSION_G_TO_MOL:
            nodes = [
                _node(1,          f'mol_{gf}',  mm_given,  f'g_{gf}'),
                _node(coeff_target, f'mol_{tf}', coeff_given, f'mol_{gf}'),
            ]
        elif ct == CONVERSION_MOL_TO_MOL:
            nodes = [
                _node(coeff_target, f'mol_{tf}', coeff_given, f'mol_{gf}'),
            ]

        return nodes


# ---------------------------------------------------------------------------
# Telemetry log (unchanged structure, extended with part_id)
# ---------------------------------------------------------------------------
class StudentTelemetryLog(models.Model):
    user         = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    problem_id   = models.CharField(max_length=50)
    part_label   = models.CharField(max_length=5, default='a')
    module_phase = models.IntegerField(default=1)
    is_correct   = models.BooleanField(default=False)
    attempts_count = models.IntegerField(default=0)
    created_at   = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Telemetry-{self.problem_id}-{self.part_label}"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------
def _get_coeff(problem, formula):
    """Return the balanced coefficient for a given formula in this reaction."""
    for entry in problem.reactants + problem.products:
        if entry['formula'] == formula:
            return entry['coeff']
    raise ValueError(f"Formula '{formula}' not found in problem {problem.problem_id}")


def _node(num_val, num_unit, den_val, den_unit):
    return {
        'num_value': round(float(num_val), 4),
        'num_unit':  num_unit,
        'den_value': round(float(den_val), 4),
        'den_unit':  den_unit,
    }