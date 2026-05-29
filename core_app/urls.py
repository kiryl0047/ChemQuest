from django.urls import path
from . import views

urlpatterns = [
    # Authentication Framework
    path('', views.student_login, name='student_login'),
    path('logout/', views.student_logout, name='student_logout'),

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

    # ── XP award endpoint (called from Module 2 & 3 JS) ──────────
    path('award-xp/', views.award_node_xp, name='award_node_xp'),

    # API endpoints
    path('api/verify-balancing/',  views.verify_balancing_backend, name='verify_balancing'),
    path('api/validate-step-node/', views.validate_step_node,      name='validate_step_node'),
]