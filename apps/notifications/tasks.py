from celery import shared_task
from datetime import timedelta
from django.utils import timezone
from django.core.cache import cache
from django.urls import reverse
from django.conf import settings
from .models import Notification
from ..orders.models import Order
from ..users.models import UserPreferences
from .utils import invalidate_notification_cache
import logging

logger = logging.getLogger(__name__)

@shared_task
def check_upcoming_deliveries():
    """Find orders due for delivery in 2 days and send reminders to their creators"""
    logger.info("Starting check for upcoming deliveries task")

    delivery_date = timezone.now().date() + timedelta(days=2)

    opted_in_users = {
        user_id
        for user_id in UserPreferences.objects.filter(
            notification_preferences__order_reminder=True
        ).values_list("user_id", flat=True)
    }
    if not opted_in_users:
        return 0

    upcoming_orders = Order.objects.filter(
        delivery_date=delivery_date, status="pending", created_by_id__in=opted_in_users
    ).select_related("created_by")

    notifications = []
    for order in upcoming_orders:
        target_url = settings.DOMAIN_NAME + reverse("api:orders:orders-detail", kwargs={"version": "v1", "pk": order.id})
        notifications.append(
            Notification(
                user=order.created_by,
                notification_type="DELIVERY_REMINDER",
                message=f"Order #{order.order_no} is due for delivery in 2 days",
                content_object=order,
                target_url=target_url,
            )
        )

    Notification.objects.bulk_create(notifications)
    for user_id in opted_in_users:
        invalidate_notification_cache(user_id)

    return len(notifications)

@shared_task
def weekly_report_notifications():
    """Send weekly report notifications to users who have opted in every Monday"""
    logger.info("Starting weekly report notifications task")

    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=7)

    base_url = settings.DOMAIN_NAME + reverse("api:analytics:analytics", kwargs={"version": "v1"})
    query_params = (
        f"?start_date={start_date.isoformat()}&end_date={end_date.isoformat()}"
    )
    target_url = f"{base_url}{query_params}"

    opted_in_users = (
        UserPreferences.objects.filter(notification_preferences__weekly_reports=True)
        .values_list("user_id", flat=True)
    )

    if not opted_in_users:
        return 0

    notifications = [
        Notification(
            user_id=user_id,
            notification_type="WEEKLY_REPORTS",
            message=f"Your weekly report is ready! Summary from {start_date} to {end_date}.",
            target_url=target_url,
        )
        for user_id in opted_in_users
    ]

    Notification.objects.bulk_create(notifications)

    for user_id in opted_in_users:
        invalidate_notification_cache(user_id)

    return len(notifications)
