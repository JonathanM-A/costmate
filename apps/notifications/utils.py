from django.core.cache import cache
from .models import Notification


def invalidate_notification_cache(user_id):
    cache.delete(f"user_{user_id}_unread_notifications")

def update_notification_cache(user_id):
    cache_key = f"user_{user_id}_unread_notifications"
    count = cache.get(cache_key)
    if count is None:
        count = Notification.objects.filter(user=user_id, is_read=False).count()
        cache.set(cache_key, count, timeout=600)
    return count