from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import models

User = get_user_model()


class Subscription(models.Model):

    TIER_CHOICES = [
        ("starter", "Starter"),
        ("pro", "Pro"),
        ("enterprise", "Enterprise"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="subscriptions"
    )
    tier = models.CharField(
        max_length=20, choices=TIER_CHOICES, default=settings.DEFAULT_SUBSCRIPTION_PLAN
    )
    customer_code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    subscription_code = models.CharField(max_length=50, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.email} - {self.tier} Subscription"
