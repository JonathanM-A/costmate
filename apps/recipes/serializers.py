from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from .models import Recipe, RecipeInventory
from ..inventory.serializers import InventoryItemSerializer, InventoryItem


class RecipeIventorySerializer(serializers.ModelSerializer):
    recipe_id = serializers.UUIDField(write_only=True)
    inventory_item_id = serializers.PrimaryKeyRelatedField(
        queryset=InventoryItem.objects.all(), write_only=True, source="inventory_item"
    )
    inventory_item = InventoryItemSerializer(read_only=True)
    cost = serializers.ReadOnlyField()

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


class IngredientSerializer(serializers.Serializer):
    inventory_item_id = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)


class RecipeSerializer(serializers.ModelSerializer):
    recipe_ingredients = RecipeIventorySerializer(
        many=True, read_only=True, source="recipeinventory_set"
    )
    ingredients = serializers.ListField(
        child=IngredientSerializer(), min_length=1, write_only=True
    )
    total_cost = serializers.ReadOnlyField()

    class Meta:
        model = Recipe
        exclude = ["inventory_items"]
        read_only_fields = [
            "id",
            "inventory_items",
            "total_cost",
            "created_by",
            "created_at",
            "updated_at",
            "is_active",
        ]

    def create(self, validated_data):
        ingredients = validated_data.pop("ingredients")
        validated_data["created_by"] = self.context["request"].user

        with transaction.atomic():
            recipe_instance = super().create(validated_data)

            for ingredient in ingredients:
                ingredient["recipe_id"] = recipe_instance.id
                serializer = RecipeIventorySerializer(
                    data=ingredient, context=self.context
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()

            recipe_instance.refresh_from_db()
            return recipe_instance
