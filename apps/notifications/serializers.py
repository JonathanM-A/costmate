from rest_framework.serializers import ModelSerializer
from .models import Notification


class NotificationSerializer(ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"
        read_only_fields = [
            "id",
            "user",
            "notification_type",
            "message",
            "content_type",
            "object_id",
            "content_object",
            "target_url",
            "created_at",
            "updated_at",
            "is_active"
        ]
        extra_kwargs = {
            "is_read": {"required": False},
        }