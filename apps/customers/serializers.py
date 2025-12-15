from rest_framework import serializers
from .models import Customer
from ..users.serializers import UserFormattedDate
from ..orders.serializers import OrderSerializer
import logging

logger = logging.getLogger(__name__)


class CustomerSerializer(serializers.ModelSerializer):
    """Serializer for Customer Model"""
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    member_since = UserFormattedDate(source="created_at")
    orders = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        exclude = ["updated_at", "is_active", "created_at"]
        read_only_fields = ["id",]

    def get_orders(self, obj):
        return OrderSerializer(obj.orders.all(), many=True, context=self.context).data

    def get_member_since(self, obj):
        return UserFormattedDate(obj.created_at).to_representation(obj.created_at)

    def update(self, instance, validated_data):
        customer = super().update(instance, validated_data)
        logger.info(f"User updated successfully: {customer.id}")
        return customer

