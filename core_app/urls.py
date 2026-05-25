from django.urls import path
from . import views

urlpatterns = [
    path('', views.preparation_ledger, name='preparation_ledger'),
    path('verify-balancing/', views.verify_balancing_backend, name='verify_balancing'),
    path('workspace/<str:prob_id>/', views.step_grid_workspace, name='step_grid_workspace'),
    path('limiting-workspace/<str:prob_id>/', views.limiting_workspace, name='limiting_workspace'),
]