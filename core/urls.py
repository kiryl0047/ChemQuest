from django.contrib import admin
from django.urls import path, include
from core_app import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core_app.urls')),
]