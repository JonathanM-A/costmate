from django.db import transaction
from django.db.models import F
from rest_framework import serializers
from .models import InventoryItem, Supplier, Inventory, InventoryHistory
import logging

logger = logging.Logger(__name__)


class InventoryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryItem
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name cannot be empty.")
        return value.strip()

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name cannot be empty.")
        return value.strip()

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class InventoryHistorySerializer(serializers.ModelSerializer):
    inventory_item = InventoryItemSerializer()
    supplier = SupplierSerializer()

    class Meta:
        model = InventoryHistory
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        is_addition = representation.pop("is_addition")
        representation["action"] = "add" if is_addition else "deduct"
        return representation

class InventorySerializer(serializers.ModelSerializer):
    inventory_item = InventoryItemSerializer()
    below_reorder = serializers.BooleanField()
    entries = serializers.ListField(
        child=serializers.DictField(allow_empty=False),
        min_length=1,
        max_length=20,
        write_only=True,
    )

    class Meta:
        model = Inventory
        fields = "__all__"
        extra_kwargs = {
            "__all__": {"read_only": True}
        }

    def validate(self, attrs):
        validated_data = super().validate(attrs)

        entries = validated_data.get("entries")
        for entry in entries:
            inventory_item_id = entry.get("item")
            quantity = entry.get("quantity")

            if not all(
                [inventory_item_id, quantity]
            ):
                raise serializers.ValidationError(
                    "Each entries must contain inventory_item_id and quantity."
                )

            if not isinstance(quantity, (int, float)) or quantity <= 0:
                raise serializers.ValidationError("Quantity must be a positive number.")

            try:
                InventoryItem.objects.get(id=inventory_item_id)
            except InventoryItem.DoesNotExist:
                raise serializers.ValidationError(
                    f"Inventory item with id {inventory_item_id} does not exist."
                )

        return validated_data

    def create(self, validated_data):
        user = self.context["request"].user
        entries = validated_data.pop("entries")

        with transaction.atomic():
            for entry in entries:
                logger.debug(f"Entry: {entry}")

                inventory_item_id = entry.get("item")
                quantity = entry.get("quantity")
                cost_price = entry.get("cost_price")
                supplier_id = entry.get("supplier_id")
                purchase_date = entry.get("purchase_date")

                inventory_item = InventoryItem.objects.get(id=inventory_item_id)
                
                # Update or create inventory
                inventory_instance, created = Inventory.objects.get_or_create(
                    inventory_item=inventory_item,
                    created_by=user,
                    defaults={"quantity": quantity}
                )
                
                if not created:
                    inventory_instance.quantity = F("quantity") + quantity
                    inventory_instance.save()
                
                inventory_instance.refresh_from_db()

                # Create history entry
                supplier = Supplier.objects.get(id=supplier_id) if supplier_id else None
                
                inventory_history_data = {
                    "inventory_item":inventory_item,
                    "quantity":quantity,
                    "supplier":supplier,
                    "cost_price":cost_price,
                    "purchase_date":purchase_date,
                    "created_by":user
                }

                serializer=InventoryHistorySerializer(data=inventory_history_data)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                logger.debug(f"Inventory history created: {serializer.data}")

        
        return inventory_instance # type: ignore