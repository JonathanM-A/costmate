# notifications/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Notification
from .utils import invalidate_notification_cache


@receiver(post_save, sender=Notification)
@receiver(post_delete, sender=Notification)
def invalidate_notification_count_cache(sender, instance, **kwargs):
    invalidate_notification_cache(instance.user_id)
