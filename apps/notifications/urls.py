from django.urls import path
from .views import (
    ListNotificationsView,
    MarkNotificationAsReadView,
    MarkAllNotificationsAsReadView,
)


urlpatterns = [
    path("notifications/", ListNotificationsView.as_view(), name="list_notifications"),
    path(
        "notifications/read-all/",
        MarkAllNotificationsAsReadView.as_view(),
        name="mark_all_notifications_as_read",
    ),
    path(
        "notifications/<uuid:id>/read/",
        MarkNotificationAsReadView.as_view(),
        name="mark_notification_as_read",
    ),
]
