from django.db import transaction
from django.db.models import F, Q, When, Case, IntegerField
from rest_framework import serializers
from djmoney.money import Money
from .models import InventoryItem, Supplier, Inventory, InventoryHistory
from ..users.utils import get_user_preferrence_from_cache
import logging

logger = logging.Logger(__name__)


class InventoryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryItem
        exclude = ["created_by", "updated_at", "created_at", "is_active", "is_default"]
        read_only_fields = [
            "created_at",
            "updated_at",
            "is_default",
            "created_by",
            "is_active",
        ]

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
        exclude = ["created_by", "updated_at", "created_at", "is_active"]
        read_only_fields = ["created_at", "updated_at", "is_active", "created_by"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name cannot be empty.")
        return value.strip()

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class InventoryHistorySerializer(serializers.ModelSerializer):
    inventory_item = InventoryItemSerializer(read_only=True)
    inventory_item_id = serializers.PrimaryKeyRelatedField(
        queryset=InventoryItem.objects.all(), source="inventory_item", write_only=True
    )
    supplier = SupplierSerializer(read_only=True)
    supplier_id = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all(),
        source="supplier",
        write_only=True,
        required=False,
    )

    class Meta:
        model = InventoryHistory
        exclude = ["created_by", "updated_at", "created_at", "is_active"]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "created_by",
        ]

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user

        if user and "inventory_item_id" in fields:
            fields["inventory_item_id"].queryset = fields[
                "inventory_item_id"
            ].queryset.filter(Q(created_by=user.id) | Q(is_default=True))

        if user and "supplier_id" in fields:
            fields["supplier_id"].queryset = fields["supplier_id"].queryset.filter(
                created_by=user.id
            )
        return fields

    def validate(self, attrs):
        validated_data = super().validate(attrs)

        is_addition = validated_data.get("is_addtion", True)
        if not is_addition:
            quantity = validated_data.get("quantity", 0)
            if quantity <= 0:
                raise serializers.ValidationError(
                    "Quantity must be greater than zero for removals."
                )
            if validated_data.get("cost_price", 0) >= 0:
                raise serializers.ValidationError(
                    "Removals should not have a cost price."
                )
        return validated_data

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        currency = get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

        representation["cost_price"] = str(Money(instance.cost_price, currency))
        representation["cost_per_unit"] = str(Money(instance.cost_per_unit, currency))
        representation["quantity"] = (
            str(instance.quantity) + instance.inventory_item.unit
        )
        return representation


class InventorySerializer(serializers.ModelSerializer):
    inventory_item = InventoryItemSerializer(read_only=True)
    below_reorder = serializers.BooleanField(read_only=True)
    entries = serializers.ListField(
        child=serializers.DictField(allow_empty=False),
        min_length=1,
        max_length=20,
        write_only=True,
    )

    class Meta:
        model = Inventory
        exclude = ["created_by", "updated_at", "created_at", "is_active"]
        read_only_fields = [
            "id",
            "inventory_item",
            "quantity",
            "total_value",
            "cost_per_unit",
            "reorder_level",
            "created_by",
            "created_at",
            "updated_at",
            "is_active",
        ]

    def validate(self, attrs):
        validated_data = super().validate(attrs)

        entries = validated_data.get("entries")
        for entry in entries:
            inventory_item_id = entry.get("inventory_item_id")
            quantity = entry.get("quantity")

            if not all([inventory_item_id, quantity]):
                raise serializers.ValidationError(
                    "Each entry must contain inventory_item_id and quantity."
                )

            if not isinstance(quantity, (int, float)) or quantity <= 0:
                raise serializers.ValidationError("Quantity must be a positive number.")

            try:
                InventoryItem.objects.filter(
                    Q(created_by=self.context["request"].user.id) | Q(is_default=True),
                    id=inventory_item_id,
                )
            except InventoryItem.DoesNotExist:
                raise serializers.ValidationError(
                    f"Inventory item with id {inventory_item_id} does not exist."
                )

        return validated_data

    def create(self, validated_data):
        user = self.context["request"].user
        entries = validated_data.pop("entries")
        modified_inventory_instances = []
        inventory_history_to_create = []

        with transaction.atomic():
            for entry in entries:
                inventory_item_id = entry.get("inventory_item_id")
                quantity = entry.get("quantity")
                cost_price = entry.get("cost_price")
                supplier_id = entry.get("supplier_id")
                incident_date = entry.get("incident_date")

                inventory_history_data = {
                    "inventory_item_id": inventory_item_id,
                    "quantity": quantity,
                    "supplier_id": supplier_id,
                    "cost_price": cost_price,
                    "incident_date": incident_date,
                    "created_by": user,
                }
                inventory_history_to_create.append(inventory_history_data)

                modified_inventory_instances.append(
                    {"id": inventory_item_id, "quantity": quantity}
                )

            # Bulk create inventory history entries
            InventoryHistory.objects.bulk_create(inventory_history_to_create)

            inventory_updates = {}
            # Aggregate quantities for each inventory item
            for item in modified_inventory_instances:
                inventory_updates[item["id"]] = (
                    inventory_updates.get(item["id"], 0) + item["quantity"]
                )

            # Get existing inventory entries that need updating
            existing_inventory = Inventory.objects.filter(
                created_by=user.id, is_active=True,
                inventory_item__id__in=inventory_updates.keys(),
            ).select_for_update()

            # Bulk create new inventory entries for items not already in inventory
            existing_ids = set(
                existing_inventory.values_list("inventory_item_id", flat=True)
            )

            missing_ids = set(inventory_updates.keys()) - existing_ids
            if missing_ids:
                Inventory.objects.bulk_create(
                    [
                        Inventory(
                            inventory_item_id=item_id,
                            quantity=inventory_updates[item_id],
                            created_by=user,
                        )
                        for item_id in missing_ids
                    ]
                )

            # Update existing inventory entries
            if existing_inventory.exists():
                case_staments = []
                for item_id, quantity in inventory_updates.items():
                    if item_id in existing_ids:
                        case_staments.append(
                            When(
                                inventory_item_id=item_id, then=F("quantity") + quantity
                            )
                        )
                Inventory.objects.filter(
                    created_by=user.id,
                    is_active=True,
                    inventory_item_id__in=existing_ids,
                ).update(quantity=Case(*case_staments, output_field=IntegerField()))
                
        return list(
            Inventory.objects.filter(
                created_by=user.id,
                is_active=True,
                inventory_item__id__in=inventory_updates.keys(),
            ).select_related("inventory_item")
        )

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        currency = get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )
        representation["total_value"] = str(Money(instance.total_value, currency))
        representation["cost_per_unit"] = str(Money(instance.cost_per_unit, currency))
        representation["quantity"] += representation["inventory_item"]["unit"]
        representation["reorder_level"] = (
            str(instance.reorder_level) + instance.inventory_item.unit
        )
        return representation
