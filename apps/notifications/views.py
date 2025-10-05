from rest_framework.generics import UpdateAPIView, ListAPIView, GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import Notification
from .serializers import NotificationSerializer
from .utils import invalidate_notification_cache, update_notification_cache


class MarkNotificationAsReadView(UpdateAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Notification.objects.none()
    serializer_class = NotificationSerializer
    http_method_names = ["patch"]
    lookup_field="id"

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if not user.is_authenticated:
            return Notification.objects.none()

        base_queryset = (
            Notification.objects.all()
            if user.is_superuser
            else Notification.objects.filter(user=user)
        )
        return base_queryset.select_related("user")

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_read = True
        instance.save()
        serializer = self.get_serializer(instance)
        invalidate_notification_cache(request.user.id)
        update_notification_cache(request.user.id)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MarkAllNotificationsAsReadView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Notification.objects.none()
    serializer_class = NotificationSerializer
    http_method_names = ["post"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if not user.is_authenticated:
            return Notification.objects.none()

        base_queryset = (
            Notification.objects.all()
            if user.is_superuser
            else Notification.objects.filter(user=user)
        )
        return base_queryset.select_related("user").order_by("-created_at")

    def post(self, request, *args, **kwargs):
        updated_count = self.get_queryset().filter(is_read=False).update(is_read=True)
        invalidate_notification_cache(request.user.id)
        update_notification_cache(request.user.id)
        return Response(
            {
                "message": f"Marked {updated_count} notifications as read.",
                "updated_count": updated_count,
            },
            status=status.HTTP_200_OK,
        )


class ListNotificationsView(ListAPIView):
    permission_classes = [IsAuthenticated]
    queryset = Notification.objects.none()
    serializer_class = NotificationSerializer
    filterset_fields = ["is_read"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if not user.is_authenticated:
            return Notification.objects.none()

        base_queryset = (
            Notification.objects.all()
            if user.is_superuser
            else Notification.objects.filter(user=user)
        )
        return base_queryset.select_related("user").order_by("-created_at")
