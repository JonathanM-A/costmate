from rest_framework import serializers
from .models import Customer
import logging

logger = logging.getLogger(__name__)


class CustomerSerializer(serializers.ModelSerializer):
    """Serializer for Customer Model"""
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Customer
        exclude = ["updated_at", "is_active", "created_at"]
        read_only_fields = ["id",]

    def update(self, instance, validated_data):
        customer = super().update(instance, validated_data)
        logger.info(f"User updated successfully: {customer.id}")
        return customer

