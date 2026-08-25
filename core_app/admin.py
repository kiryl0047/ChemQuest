from django.contrib import admin
from .models import (
    StoichiometryProblem, ProblemPart, Substance,
    StudentTelemetryLog, ProblemProgress, PartProgress, SynthesisAttempt,
)

admin.site.register(StoichiometryProblem)
admin.site.register(ProblemPart)
admin.site.register(Substance)
admin.site.register(StudentTelemetryLog)
admin.site.register(ProblemProgress)
admin.site.register(PartProgress)
admin.site.register(SynthesisAttempt)
