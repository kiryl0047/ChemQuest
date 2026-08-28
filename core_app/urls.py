from django.urls import path
from . import views

urlpatterns = [
    # Authentication Framework
    path('', views.student_login, name='student_login'),
    path('logout/', views.student_logout, name='student_logout'),
    path('register/', views.register, name='register'),

    # Lobby — problem selection
    path('problem_lobby/', views.problem_lobby, name='problem_lobby'),
    path('problem/reset/<str:prob_id>/', views.reset_problem_telemetry, name='reset_problem_telemetry'),

    # Module 1 — Preparation Ledger
    path('ledger/',                          views.preparation_ledger, name='preparation_ledger_default'),
    path('ledger/<str:prob_id>/',            views.preparation_ledger, name='preparation_ledger'),

    # Module 2 — Step-Grid Workspace
    path('workspace/<str:prob_id>/<str:part_label>/', views.step_grid_workspace, name='step_grid_workspace'),

    # Module 3 — Limiting Reagent Workspace
    path('limiting-workspace/<str:prob_id>/',                    views.limiting_workspace, name='limiting_workspace'),
    path('limiting-workspace/<str:prob_id>/<str:part_label>/',   views.limiting_workspace, name='limiting_workspace_part'),

    # Module 4 — Student Self-Optimization Dashboard
    path('dashboard/', views.student_dashboard, name='student_dashboard'),
    path('dashboard/export/pdf/', views.dashboard_export_pdf, name='dashboard_export_pdf'),

    # Instructor-only analytics (is_staff scope)
    path('dashboard/instructor/', views.instructor_dashboard, name='instructor_dashboard'),

    # Synthesis Challenge — randomized unassisted review
    path('synthesis/', views.synthesis_challenge, name='synthesis_challenge'),
    path('api/synthesis-submit/', views.synthesis_submit, name='synthesis_submit'),

    # ── XP award endpoint (legacy client-driven) ──────────
    path('award-xp/', views.award_node_xp, name='award_node_xp'),

    # API endpoints
    path('api/verify-balancing/',    views.verify_balancing_backend,  name='verify_balancing'),
    path('api/verify-molar-mass/',   views.verify_molar_mass_backend, name='verify_molar_mass'),
    path('api/m1-checkpoint/',       views.m1_checkpoint,             name='m1_checkpoint'),
    path('api/m1-retrieval/',        views.m1_retrieval_check,        name='m1_retrieval'),
path('api/audit-chain/',         views.audit_chain,                name='audit_chain'),
path('api/verify-node/',         views.verify_node,                name='verify_node'),
    path('api/constants/<str:prob_id>/', views.api_locked_constants,  name='api_locked_constants'),
]
