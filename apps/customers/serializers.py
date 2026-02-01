from djmoney.money import Money
from rest_framework import serializers
from .models import Customer
from ..users.serializers import UserFormattedDate
from ..users.utils import get_user_preferrence_from_cache
from ..orders.serializers import CustomerOrderSerializer
import logging

logger = logging.getLogger(__name__)


class CustomerSerializer(serializers.ModelSerializer):
    """Serializer for Customer Model"""

    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    member_since = UserFormattedDate(
        source="created_at", required=False, read_only=True
    )
    total_orders = serializers.IntegerField(read_only=True)
    order_value = serializers.SerializerMethodField()
    average_order_value = serializers.SerializerMethodField()
    orders = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        exclude = ["updated_at", "is_active", "created_at", "created_by"]
        read_only_fields = ["id", "member_since", "orders"]

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

    def get_orders(self, obj):
        # Uses prefetched orders from the view (already filtered by is_active=True)
        orders = obj.orders.all()
        return CustomerOrderSerializer(orders, many=True, context=self.context).data

    def get_order_value(self, obj):
        order_value = getattr(obj, "order_value", 0)
        if order_value is not None:
            return str(Money(order_value, self.currency))
        return str(Money(0, self.currency))

    def get_average_order_value(self, obj):
        average_order_value = getattr(obj, "average_order_value", 0)
        if average_order_value is not None:
            return str(Money(average_order_value, self.currency))
        return str(Money(0, self.currency))
    
    def get_member_since(self, obj):
        return UserFormattedDate(obj.created_at).to_representation(obj.created_at)

    def update(self, instance, validated_data):
        customer = super().update(instance, validated_data)
        logger.info(f"User updated successfully: {customer.id}")
        return customer


class CustomerListSerializer(serializers.ModelSerializer):
    """Serializer for retrieving Customer details with related orders"""

    member_since = UserFormattedDate(
        source="created_at", required=False, read_only=True
    )
    total_orders = serializers.IntegerField(read_only=True)
    order_value = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        exclude = ["updated_at", "is_active"]
        read_only_fields = ["id", "member_since"]

    def get_member_since(self, obj):
        return UserFormattedDate(obj.created_at).to_representation(obj.created_at)

    def get_order_value(self, obj):
        currency = get_user_preferrence_from_cache(
            self.context["request"].user, "currency", "USD"
        )
        order_value = getattr(obj, "order_value", 0)
        if order_value is not None:
            return str(Money(order_value, currency))
        return str(Money(0, currency))
