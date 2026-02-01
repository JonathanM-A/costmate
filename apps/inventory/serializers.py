from decimal import Decimal
from djmoney.money import Money
from babel.numbers import get_currency_symbol
from django.db.models import Q
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator
from .models import InventoryItem, Supplier, Inventory, InventoryHistory, InventoryUnit
from .services import InventoryUpdateService
from ..users.utils import get_user_preferrence_from_cache
import logging

logger = logging.Logger(__name__)


class InventoryUnitSerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    
    class Meta:
        model = InventoryUnit
        exclude = ["updated_at", "created_at", "is_active"]

        extra_kwargs = {
            "is_default": {"read_only": True},
        }


class InventoryItemSerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = InventoryItem
        exclude = ["updated_at", "created_at", "is_active"]

        extra_kwargs = {
            "is_default": {"read_only": True},
        }

    def validate_unit(self, value):
        if value and not InventoryUnit.objects.filter(unit_symbol=value).exists():
            raise serializers.ValidationError(
                f"This unit symbol '{value}' is not pre-registered"
            )
        return value

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name cannot be empty.")
        return value.strip()

    def to_representation(self, instance):
        user = self.context["request"].user
        data = super().to_representation(instance)

        related_inventory = getattr(instance, "user_inventory", instance.inventory.filter(created_by=user, is_active=True))
        cost_record = next((i for i in related_inventory), None)

        data["cost_per_unit"] = (
            cost_record.cost_per_unit if cost_record else Decimal("0.00")
        )
        return data

class SupplierSerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    products = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        exclude = ["updated_at", "created_at", "is_active"]
        read_only_fields = ["id", "total_spent"]

        validators = [
            UniqueTogetherValidator(
                queryset=Supplier.objects.filter(is_active=True),
                fields=["contact", "name", "created_by"],
                message="Supplier with this contact already exists.",
            )
        ]

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

    def get_products(self, obj):
        products_qs = (
            obj.history.all()
            .order_by("inventory_item__name", "-incident_date")
            .distinct("inventory_item__name")
        )
        products = products_qs.values_list("inventory_item__name", flat=True)
        return products

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name cannot be empty.")
        return value.strip()

    def create(self, validated_data):
        name = validated_data.get("name")
        contact = validated_data.get("contact")
        if Supplier.objects.filter(
            created_by=validated_data["created_by"],
            contact=contact,
            name=name,
            is_active=False,
        ).exists():
            supplier = Supplier.objects.get(
                created_by=validated_data["created_by"],
                contact=contact,
                is_active=False,
            )
            supplier.activate()
            return supplier
        return super().create(validated_data)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["total_spent"] = str(
            Money(
                instance.total_spent,
                self.currency,
            )
        )
        return representation


class InventoryHistorySerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
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
        exclude = ["updated_at", "created_at", "is_active"]
        read_only_fields = [
            "id",
        ]

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )
    
    @property
    def symbol(self):
        return get_currency_symbol(self.currency, locale="en_US")
    
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

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        cost_price_money = Money(instance.cost_price, self.currency)
        cost_per_unit_money = Money(instance.cost_per_unit, self.currency)

        representation["cost_price"] = str(cost_price_money)
        representation["cost_per_unit"] = f"{self.symbol}{cost_per_unit_money.amount:.4f}"

        representation["quantity"] = (
            str(instance.quantity) + instance.inventory_item.unit
        )
        return representation


class InventorySerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
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
        exclude = ["updated_at", "created_at", "is_active"]
        read_only_fields = [
            "id",
            "inventory_item",
            "quantity",
            "total_value",
            "cost_per_unit",
            "reorder_level",
            "days_of_stock_on_hand",
        ]

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )
    
    @property
    def symbol(self):
        return get_currency_symbol(self.currency, locale="en_US")

    def validate(self, attrs):
        validated_data = super().validate(attrs)

        entries = validated_data.get("entries")
        user = self.context["request"].user

        # Collect all inventory item IDs for bulk validation
        inventory_item_ids = []
        for entry in entries:
            inventory_item_id = entry.get("inventory_item_id")
            quantity = entry.get("quantity")

            if not all([inventory_item_id, quantity]):
                raise serializers.ValidationError(
                    "Each entry must contain inventory_item_id and quantity."
                )

            if not isinstance(quantity, (int, float)) or quantity <= 0:
                raise serializers.ValidationError("Quantity must be a positive number.")

            inventory_item_ids.append(inventory_item_id)

        # Validate all inventory items exist in a single query
        valid_items = set(
            InventoryItem.objects.filter(
                Q(created_by=user.id) | Q(is_default=True),
                id__in=inventory_item_ids,
            ).values_list("id", flat=True)
        )

        for item_id in inventory_item_ids:
            if item_id not in valid_items:
                raise serializers.ValidationError(
                    f"Inventory item with id {item_id} does not exist."
                )

        return validated_data

    def create(self, validated_data):
        user = self.context["request"].user
        entries = validated_data.pop("entries")
        return InventoryUpdateService.process_inventory_updates(user, entries)

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        total_money = Money(instance.total_value, self.currency)
        cost_money = Money(instance.cost_per_unit, self.currency)

        representation["total_value"] = f"{self.symbol}{total_money.amount:.4f}"
        representation["cost_per_unit"] = f"{self.symbol}{cost_money.amount:.4f}"

        representation["quantity"] += representation["inventory_item"]["unit"]
        representation["reorder_level"] = (
            str(instance.reorder_level) + instance.inventory_item.unit
        )
        return representation
