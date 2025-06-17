from rest_framework import serializers
from .models import Customer, CustomerType
import logging

logger = logging.getLogger(__name__)


class CustomerTypeSerializer(serializers.ModelSerializer):
    """Serializre for CustomerType model"""

    class Meta:
        model = CustomerType
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class CustomerSerializer(serializers.ModelSerializer):
    """Serializer for Customer Model"""

    customer_type_detail = CustomerTypeSerializer(
        source="customer_type", read_only=True
    )

    class Meta:
        model = Customer
        fields = "__all__"
        read_only_fields = ("id", "is_active", "created_at", "updated_at", "created_by")

    def validate(self, data):  # type: ignore
        # Validate customer_type
        customer_type = data.get("customer_type")
        custom_customer_type = data.get("custom_customer_type")

        try:
            # if custom_type is provided, type should be "other"
            if custom_customer_type:
                if not customer_type or customer_type != "other":
                    raise serializers.ValidationError(
                        {
                            "error": "Must select 'Other' as customer type when providing a custom type"
                        }
                    )

            # if customer_type is "other", custom_customer_type must be provided
            if customer_type == "other" and not custom_customer_type:
                raise serializers.ValidationError(
                    {
                        "error": "Custom customer type is required when 'Other' is selected."
                    }
                )
            return data

        except serializers.ValidationError as e:
            logger.error(f"CustomerSerializer Validation error: {str(e)}")
            raise

    def to_representation(self, instance):
        try:
            representation = super().to_representation(instance)
            representation["customer_type"] = instance.display_customer_type
            return representation
        except Exception as e:
            logger.error(f"Error creating customer representation: {str(e)}")
            raise

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
