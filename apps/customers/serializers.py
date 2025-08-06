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
        try:
            validated_data["created_by"] = self.context["request"].user
            return super().create(validated_data)
        except Exception as e:
            logger.error(f"Error creating customer: {str(e)}")
            raise

    def update(self, instance, validated_data):
        try:
            customer = super().update(instance, validated_data)
            logger.info(f"User updated successfully: {customer.id}")
            return customer
        except Exception as e:
            logger.error(f"Error updating customer: {str(e)}")
            raise
