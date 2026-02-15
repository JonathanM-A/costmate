from django.urls import path
from .views import (
    UserView,
    BusinessView,
    UserPreferencesView,
    OnboardingMetricsView,
)


urlpatterns = [
    path("profile/", UserView.as_view(), name="user-profile"),
    path("business/", BusinessView.as_view(), name="user-business"),
    path("preferences/", UserPreferencesView.as_view(), name="user-preferences"),
    path("onboarding/", OnboardingMetricsView.as_view(), name="onboarding-metrics"),
]
