from django.urls import path
from .views import AnalyticsView, AnalyticsExportView

app_name = 'analytics'

urlpatterns = [
    path('analytics/export/', AnalyticsExportView.as_view(), name='analytics-export'),
    path('analytics/', AnalyticsView.as_view(), name='analytics'),
]