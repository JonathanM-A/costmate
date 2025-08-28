from datetime import timedelta
from django.utils import timezone
from django.core.cache import cache
from django.urls import reverse
from .models import Notification
from ..orders.models import Order


def check_upcoming_deliveries():
    delivery_date = timezone.now().date() + timedelta(days=2)
    upcoming_orders = Order.objects.filter(
        delivery_date=delivery_date,
        status="pending"
    )

    for order in upcoming_orders:
        target_url = reverse("orders:order-detail", args=[order.id])
        Notification.objects.create(
            user=order.created_by,
            notification_type="DELIVERY_REMINDER",
            message=f"Order #{order.id} is due for delivery in 2 days",
            content_object=order,
            target_url=target_url
        )
    
    return upcoming_orders.count()


def invalidate_notification_cache(user_id):
    cache.delete(f"user_{user_id}_unread_notifications")


def update_notification_cache(user_id):
    count = Notification.objects.filter(user=user_id, is_read=False).count()
    cache.set(f"user_{user_id}_unread_notifications", count, timeout=600)
    return count