import uuid
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import models

User = get_user_model()

def get_default_subscription_tier():
    return settings.DEFAULT_SUBSCRIPTION_PLAN


class Subscription(models.Model):

    TIER_CHOICES = [
        ("UK_M", "UK Monthly"),
        ("UK_Y", "UK Yearly"),
    ]

    id = None
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="subscriptions", primary_key=True
    )
    tier = models.CharField(
        max_length=20, choices=TIER_CHOICES, default=get_default_subscription_tier
    )
    current_sub_start = models.DateTimeField(auto_now_add=True)
    current_sub_end = models.DateTimeField(null=True, blank=True)
    subscription_code = models.CharField(max_length=50, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.email} - {self.tier} Subscription"
