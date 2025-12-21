from django.urls import path
from .views import SMTPHealthCheckView

urlpatterns = [
    path('smtp-health-check/', SMTPHealthCheckView.as_view(), name='smtp-health-check'),
]