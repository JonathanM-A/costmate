from django.urls import path
from .views import CreateSubscriptionView
from .webhook import paystack_webhook

urlpatterns = [
    path("subscribe/", CreateSubscriptionView.as_view(), name="subscribe"),
    path("webhook/paystack/", paystack_webhook, name="paystack-webhook"),
]