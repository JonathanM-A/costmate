from decimal import Decimal
from djmoney.money import Money
from django.db.models import Q
from rest_framework import serializers
from .models import Recipe, RecipeInventory, RecipeCategory, RecipeStep
from .services import RecipeService
from ..inventory.serializers import InventoryItemSerializer, InventoryItem
from ..users.utils import get_user_preferrence_from_cache
import logging

logger = logging.Logger(__name__)


class RecipeCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = RecipeCategory
        fields = ["id", "name", "description", "created_by"]
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
            self.context["request"].user.id, "currency", "USD"
        )
        representation["cost"] = str(Money(instance.cost, currency))
        representation["quantity"] = (
            str(instance.quantity) + instance.inventory_item.unit
        )
        return representation


class IngredientSerializer(serializers.Serializer):
    inventory_item_id = serializers.PrimaryKeyRelatedField(
        queryset=InventoryItem.objects.all(), write_only=True
    )
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=0)
    suggested_cost = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        required=False,
        default=Decimal("0.00"),
    )
    unit = serializers.CharField(max_length=10, required=False, allow_null=True)

    class Meta:
        extra_kwargs = {
            "unit": {"required": False, "allow_null": True, "write_only": True},
        }
    

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user
        fields["inventory_item_id"].queryset = InventoryItem.objects.filter(
            Q(is_default=True) | Q(created_by=user.id)
        )
        return fields

    def validate_inventory_item_id(self, value):
        return value.id


class RecipeSerializer(serializers.ModelSerializer):

    ingredients = serializers.ListField(
        child=IngredientSerializer(), min_length=1, write_only=True
    )
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=RecipeCategory.objects.all(),
        write_only=True,
        source="category",
        required=False,
    )
    category = serializers.StringRelatedField(read_only=True)
    shareable_link = serializers.SerializerMethodField()

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )


    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user

        if user and "category_id" in fields:
            fields["category_id"].queryset = fields["category_id"].queryset.filter(
                Q(created_by=user.id)|Q(is_default=True)
            )
        return fields

    def get_shareable_link(self, obj):
        if obj.share_enabled:
            return obj.get_shareable_link()
        return None

    class Meta:
        model = Recipe
        fields = [
            "id",
            "name",
            "category",
            "labour_time",
            "labour_rate",
            "ingredients",
            "category_id",
            "total_cost",
            "is_draft",
            "shareable_link",
        ]
        read_only_fields = ["id", "total_cost"]
        extra_kwargs = {
            "labour_time": {"write_only": True},
            "labour_rate": {"write_only": True},
        }

    def create(self, validated_data):
        user = self.context["request"].user
        return RecipeService.create_recipe(user, validated_data)

    def update(self, instance, validated_data):
        return RecipeService.update_recipe(instance, validated_data)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if "total_cost" in representation:
            representation["total_cost"] = str(Money(representation["total_cost"], self.currency))
        return representation


class RecipeDetailSerializer(serializers.ModelSerializer):
    recipe_ingredients = RecipeIventorySerializer(
        many=True, read_only=True, source="ingredients"
    )
    ingredients = serializers.ListField(
        child=IngredientSerializer(), min_length=1, write_only=True
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
            "created_by",
            "created_at",
            "updated_at",
            "is_active",
        ]

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        money_fields = [
            "inventory_items_cost",
            "labour_cost",
            "total_cost",
        ]
        for field in money_fields:
            if field in representation:
                amount = representation[field]
                representation[field] = str(Money(amount, self.currency))
        return representation


class RecipeStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecipeStep
        fields = ["id", "step_number", "heading", "description"]
        read_only_fields = ["id"]
