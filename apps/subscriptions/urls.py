from django.urls import path
from .views import CreateSubscriptionView
from .webhook import stripe_webhook

urlpatterns = [
    path("subscribe/", CreateSubscriptionView.as_view(), name="subscribe"),
    path("webhook/", stripe_webhook, name="stripe-webhook"),
]