from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order
from .services import OrderNotificationService


@receiver(post_save, sender=Order)
def check_reorder_levels(sender, instance, created, **kwargs):
    if instance.status == "completed":
        OrderNotificationService.check_reorder_levels(instance)
