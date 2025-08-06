from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from djmoney.money import Money
from .models import Recipe, RecipeInventory, RecipeCategory
from ..inventory.serializers import InventoryItemSerializer, InventoryItem
from ..users.utils import get_user_preferrence_from_cache
import logging

logger = logging.Logger(__name__)


class RecipeCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = RecipeCategory
        fields = ["id", "name", "description"]
        read_only_fields = ["id", "created_by", "created_at", "updated_at", "is_active"]

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class RecipeIventorySerializer(serializers.ModelSerializer):
    recipe_id = serializers.UUIDField(write_only=True)
    inventory_item_id = serializers.PrimaryKeyRelatedField(
        queryset=InventoryItem.objects.all(), write_only=True, source="inventory_item"
    )
    inventory_item = InventoryItemSerializer(read_only=True)

    class Meta:
        model = RecipeInventory
        exclude = ["recipe"]
        read_only_fields = ["recipe", "inventory_item", "cost"]

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user

        if user and "inventory_item_id" in fields:
            fields["inventory_item_id"].queryset = fields[
                "inventory_item_id"
            ].queryset.filter(Q(is_default=True) | Q(created_by=user.id))
        return fields

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        currency = get_user_preferrence_from_cache(
            self.context["request"].user, "currency", "USD"
        )
        representation["cost"] = str(Money(instance.cost, currency))
        representation["quantity"] = (
            str(instance.quantity) + instance.inventory_item.unit
        )
        return representation


class IngredientSerializer(serializers.Serializer):
    inventory_item_id = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)

    def validate_inventory_item_id(self, value):
        user = self.context["request"].user
        if not InventoryItem.objects.filter(
            Q(is_default=True) | Q(created_by=user.id), id=value
        ).exists():
            raise serializers.ValidationError("Invalid inventory item ID.")
        return value


class RecipeSerializer(serializers.ModelSerializer):
    recipe_ingredients = RecipeIventorySerializer(
        many=True, read_only=True, source="ingredients"
    )
    ingredients = serializers.ListField(
        child=IngredientSerializer(), min_length=1, write_only=True
    )
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=RecipeCategory.objects.all(), write_only=True, source="category"
    )
    category = RecipeCategorySerializer(read_only=True)

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user

        if user and "category_id" in fields:
            fields["category_id"].queryset = fields["category_id"].queryset.filter(
                created_by=user.id
            )
        return fields

    class Meta:
        model = Recipe
        exclude = [
            "inventory_items",
            "created_by",
            "created_at",
            "updated_at",
            "is_active",
        ]
        read_only_fields = [
            "id",
            "recipe_ingredients",
            "inventory_items",
            "inventory_items_cost",
            "labour_cost",
            "total_cost",
            "cost_price",
            "selling_price",
            "created_by",
            "created_at",
            "updated_at",
            "is_active",
        ]

    def create(self, validated_data):
        ingredients = validated_data.pop("ingredients")
        validated_data["created_by"] = self.context["request"].user

        profit_margin = validated_data.get("profit_margin", None)
        labour_rate = validated_data.get("labour_rate", None)

        if not profit_margin:
            default_profit_margin = get_user_preferrence_from_cache(
                self.context["request"].user, "profit_margin", 30.00
            )
            validated_data["profit_margin"] = default_profit_margin
        if not labour_rate:
            default_labour_rate = get_user_preferrence_from_cache(
                self.context["request"].user, "labour_rate", 20.00
            )
            validated_data["labour_rate"] = default_labour_rate

        with transaction.atomic():
            recipe_instance = super().create(validated_data)

            for ingredient in ingredients:
                ingredient["recipe_id"] = recipe_instance.id
                serializer = RecipeIventorySerializer(
                    data=ingredient, context=self.context
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()

            recipe_instance.save()

            return recipe_instance

    def update(self, instance, validated_data):
        ingredients = validated_data.pop("ingredients", None)
        validated_data["created_by"] = self.context["request"].user

        with transaction.atomic():
            instance = super().update(instance, validated_data)

            if ingredients is not None:
                # Clear existing ingredients
                instance.ingredients.all().delete()

                for ingredient in ingredients:
                    ingredient["recipe_id"] = instance.id
                    serializer = RecipeIventorySerializer(
                        data=ingredient, context=self.context
                    )
                    serializer.is_valid(raise_exception=True)
                    serializer.save()

            instance.save()

            return instance

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["profit_margin"] = str(instance.profit_margin) + "%"
        currency = get_user_preferrence_from_cache(
            self.context["request"].user, "currency", "USD"
        )
        money_fields = [
            "inventory_items_cost",
            "labour_cost",
            "packaging_cost",
            "overhead_cost",
            "cost_price",
            "selling_price",
        ]
        for field in money_fields:
            if field in representation:
                amount = representation[field]
                representation[field] = str(Money(amount, currency))
        return representation
