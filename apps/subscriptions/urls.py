from django.urls import path
from .views import CreateSubscriptionView, CancelSubscriptionView, ChangeSubscriptionView
from .webhook import stripe_webhook

urlpatterns = [
    path("subscribe/", CreateSubscriptionView.as_view(), name="subscribe"),
    path("cancel/", CancelSubscriptionView.as_view(), name="cancel"),
    path("change/", ChangeSubscriptionView.as_view(), name="change"),
    path("webhook/", stripe_webhook, name="stripe-webhook"),
]