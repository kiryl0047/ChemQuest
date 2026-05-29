from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# ---------------------------------------------------------------------------
# XP & Level constants
# ---------------------------------------------------------------------------
XP_PER_NODE_CORRECT   = 25    # awarded per correctly validated fraction node
XP_PER_PART_COMPLETE  = 50    # bonus when all nodes in a part are verified
XP_PER_BALANCE        = 30    # awarded for correctly balancing an equation
XP_PER_LIMITING_TRACK = 40    # awarded per verified limiting-reagent track
XP_PER_DEDUCTION      = 100   # awarded for correct limiting-reagent deduction
 
XP_PER_LEVEL = 500            # XP needed to advance one level

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
# UserProfile -- XP and level tracking
# ---------------------------------------------------------------------------
class UserProfile(models.Model):
    user     = models.OneToOneField(User, on_delete=models.CASCADE,
                                    related_name='profile')
    total_xp = models.IntegerField(default=0)
 
    def __str__(self):
        return f"{self.user.username} -- LVL {self.level} ({self.total_xp} XP)"
 
    @property
    def level(self):
        """Player level, starting at 1. Increases every XP_PER_LEVEL XP."""
        return max(1, self.total_xp // XP_PER_LEVEL + 1)
 
    @property
    def xp_into_current_level(self):
        """XP earned within the current level (resets each level-up)."""
        return self.total_xp % XP_PER_LEVEL
 
    @property
    def level_progress_pct(self):
        """0-100 float representing progress through the current level."""
        return round((self.xp_into_current_level / XP_PER_LEVEL) * 100, 1)

# ---------------------------------------------------------------------------
# Signal: auto-create a UserProfile whenever a new User is saved
# ---------------------------------------------------------------------------
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
 
 
@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()

# ---------------------------------------------------------------------------
# Top-level reaction problem
# ---------------------------------------------------------------------------
class StoichiometryProblem(models.Model):
    problem_id            = models.CharField(max_length=50, unique=True)
    title                 = models.CharField(max_length=200)
    prompt                = models.TextField()
    reactants_str         = models.CharField(max_length=200)
    products_str          = models.CharField(max_length=200)
    correct_coefficients  = models.CharField(max_length=50)
    is_limiting_problem   = models.BooleanField(default=False)
 
    def __str__(self):
        return f"[{self.problem_id}] {self.title}"
 
    def parse_side(self, side_str):
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
# Telemetry log
# ---------------------------------------------------------------------------
class StudentTelemetryLog(models.Model):
    user           = models.ForeignKey(User, on_delete=models.CASCADE,
                                       null=True, blank=True)
    problem_id     = models.CharField(max_length=50)
    part_label     = models.CharField(max_length=10, default='a')
    module_phase   = models.IntegerField(default=1)
    is_correct     = models.BooleanField(default=False)
    attempts_count = models.IntegerField(default=0)
    created_at     = models.DateTimeField(auto_now_add=True)
 
    def __str__(self):
        return f"Telemetry-{self.problem_id}-{self.part_label}"

# ---------------------------------------------------------------------------
# Chemical substance registry
# ---------------------------------------------------------------------------
class Substance(models.Model):
    formula      = models.CharField(max_length=30, unique=True)
    display_name = models.CharField(max_length=80)
    molar_mass   = models.DecimalField(max_digits=10, decimal_places=4)
 
    def __str__(self):
        return f"{self.formula} ({self.molar_mass} g/mol)"

# ---------------------------------------------------------------------------
# Top-level reaction problem
# ---------------------------------------------------------------------------
class StoichiometryProblem(models.Model):
    problem_id            = models.CharField(max_length=50, unique=True)
    title                 = models.CharField(max_length=200)
    prompt                = models.TextField()
    reactants_str         = models.CharField(max_length=200)
    products_str          = models.CharField(max_length=200)
    correct_coefficients  = models.CharField(max_length=50)
    is_limiting_problem   = models.BooleanField(default=False)
 
    def __str__(self):
        return f"[{self.problem_id}] {self.title}"
 
    def parse_side(self, side_str):
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
# Sub-question / part
# ---------------------------------------------------------------------------
class ProblemPart(models.Model):
    problem          = models.ForeignKey(StoichiometryProblem, on_delete=models.CASCADE,
                                         related_name='parts')
    part_label       = models.CharField(max_length=10)
    part_prompt      = models.TextField()
    given_substance  = models.ForeignKey(Substance, on_delete=models.PROTECT,
                                         related_name='given_parts')
    given_quantity   = models.DecimalField(max_digits=12, decimal_places=4)
    given_unit       = models.CharField(max_length=10, default='g')
    target_substance = models.ForeignKey(Substance, on_delete=models.PROTECT,
                                         related_name='target_parts')
    target_unit      = models.CharField(max_length=10, default='g')
    conversion_type  = models.CharField(max_length=20, choices=CONVERSION_CHOICES,
                                        default=CONVERSION_G_TO_G)
    correct_answer   = models.DecimalField(max_digits=14, decimal_places=4)
    is_limiting_part = models.BooleanField(default=False)
    order            = models.PositiveSmallIntegerField(default=0)
    
    limiting_given_quantities = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['order']
        unique_together = [('problem', 'part_label')]
 
    def __str__(self):
        return f"{self.problem.problem_id} Part {self.part_label}"
 
    @property
    def node_count(self):
        return NODE_COUNT[self.conversion_type]
 
    def expected_nodes(self):
        problem   = self.problem
        gf        = self.given_substance.formula
        tf        = self.target_substance.formula
        mm_given  = float(self.given_substance.molar_mass)
        mm_target = float(self.target_substance.molar_mass)
 
        coeff_given  = _get_coeff(problem, gf)
        coeff_target = _get_coeff(problem, tf)
 
        ct    = self.conversion_type
        nodes = []
 
        if ct == CONVERSION_G_TO_G:
            nodes = [
                _node(1,            f'mol_{gf}', mm_given,    f'g_{gf}'),
                _node(coeff_target, f'mol_{tf}', coeff_given, f'mol_{gf}'),
                _node(mm_target,    f'g_{tf}',   1,           f'mol_{tf}'),
            ]
        elif ct == CONVERSION_MOL_TO_G:
            nodes = [
                _node(coeff_target, f'mol_{tf}', coeff_given, f'mol_{gf}'),
                _node(mm_target,    f'g_{tf}',   1,           f'mol_{tf}'),
            ]
        elif ct == CONVERSION_G_TO_MOL:
            nodes = [
                _node(1,            f'mol_{gf}', mm_given,    f'g_{gf}'),
                _node(coeff_target, f'mol_{tf}', coeff_given, f'mol_{gf}'),
            ]
        elif ct == CONVERSION_MOL_TO_MOL:
            nodes = [
                _node(coeff_target, f'mol_{tf}', coeff_given, f'mol_{gf}'),
            ]
 
        return nodes


# ---------------------------------------------------------------------------
# Telemetry log
# ---------------------------------------------------------------------------
class StudentTelemetryLog(models.Model):
    user           = models.ForeignKey(User, on_delete=models.CASCADE,
                                       null=True, blank=True)
    problem_id     = models.CharField(max_length=50)
    part_label     = models.CharField(max_length=10, default='a')
    module_phase   = models.IntegerField(default=1)
    is_correct     = models.BooleanField(default=False)
    attempts_count = models.IntegerField(default=0)
    created_at     = models.DateTimeField(auto_now_add=True)
 
    def __str__(self):
        return f"Telemetry-{self.problem_id}-{self.part_label}"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------
def _get_coeff(problem, formula):
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