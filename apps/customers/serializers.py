from rest_framework import serializers
from .models import Customer
import logging

logger = logging.getLogger(__name__)


class CustomerSerializer(serializers.ModelSerializer):
    """Serializer for Customer Model"""

    class Meta:
        model = Customer
        exclude = ["updated_at", "is_active", "created_by"]
        read_only_fields = ("id", "is_active", "created_at", "updated_at", "created_by")

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


    def update(self, instance, validated_data):
        customer = super().update(instance, validated_data)
        logger.info(f"User updated successfully: {customer.id}")
        return customer

