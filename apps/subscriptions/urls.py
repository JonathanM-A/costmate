from django.urls import path
from .views import (
    CreateSubscriptionView,
    CancelSubscriptionView,
    ChangeSubscriptionView,
    SubscriptionDetailsView,
    VerifySubscriptionView
)
from .webhook import stripe_webhook

app_name = "subscription"

urlpatterns = [
    path("", CreateSubscriptionView.as_view(), name="subscribe"),
    path("cancel/", CancelSubscriptionView.as_view(), name="cancel-subscription"),
    path("change/", ChangeSubscriptionView.as_view(), name="change-subscription"),
    path("details/", SubscriptionDetailsView.as_view(), name="subscription-details"),
    path("verify/", VerifySubscriptionView.as_view(), name="verify-subscription"),
    path("webhook/", stripe_webhook, name="stripe-webhook"),
]
