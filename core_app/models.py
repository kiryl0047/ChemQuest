from django.db import models
from django.contrib.auth.models import User

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
