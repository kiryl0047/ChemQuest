from django.urls import path
from . import views

urlpatterns = [
    # Lobby — problem selection
    path('', views.problem_lobby, name='problem_lobby'),

    # Module 1 — Preparation Ledger
    path('ledger/',                          views.preparation_ledger, name='preparation_ledger_default'),
    path('ledger/<str:prob_id>/',            views.preparation_ledger, name='preparation_ledger'),

    # Module 2 — Step-Grid Workspace
    path('workspace/<str:prob_id>/<str:part_label>/', views.step_grid_workspace, name='step_grid_workspace'),

    # Module 3 — Limiting Reagent Workspace
    path('limiting-workspace/<str:prob_id>/<str:part_label>/', views.limiting_workspace, name='limiting_workspace'),

    # API endpoints
    path('api/verify-balancing/',  views.verify_balancing_backend, name='verify_balancing'),
    path('api/validate-step-node/', views.validate_step_node,      name='validate_step_node'),
]