from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from ..common.models import BaseModel

User = get_user_model()


class Notification(BaseModel):
    NOTIFICATION_TYPES = (
        ("REORDER_CHECK", "Reorder level check"),
        ("DELIVERY_REMINDER", "Delivery reminder"),
    )

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")
    target_url = models.URLField(max_length=500, blank=True, null=True)

    class Meta: # type: ignore
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["user", "is_read", "created_at"]),
            models.Index(fields=["user", "is_read"]),
        ]
