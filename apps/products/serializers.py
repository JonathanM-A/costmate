from functools import cached_property
from django.db.models import Q
from rest_framework import serializers
from djmoney.money import Money
from .models import Product, ProductRecipes, ProductCategory
from apps.recipes.models import Recipe
from apps.users.utils import get_user_preferrence_from_cache
from .services import ProductService


class ProductCategorySerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = ProductCategory
        exclude = ["created_at", "updated_at", "is_active", "is_default"]
        read_only_fields = ["id"]


class ProductRecipesSerializer(serializers.ModelSerializer):
    recipe_name = serializers.SerializerMethodField()
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = ProductRecipes
        fields = [
            "id",
            "recipe",
            "recipe_name",
            "quantity",
            "cost",
            "created_by",
        ]
        extra_kwargs = {
            "cost": {"read_only": True},
            "recipe": {"write_only": True},
        }

    def get_recipe_name(self, obj):
        return obj.recipe.name if obj.recipe else None


class RecipeItemSerializer(serializers.Serializer):
    recipe_id = serializers.PrimaryKeyRelatedField(
        queryset=Recipe.objects.all(), write_only=True
    )
    quantity = serializers.IntegerField(min_value=1)

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user
        fields["recipe_id"].queryset = Recipe.objects.filter(created_by=user.id)
        return fields

    def validate_recipe_id(self, value):
        return value.id


class ProductSerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    recipes = serializers.ListField(
        child=RecipeItemSerializer(), min_length=1, write_only=True
    )
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductCategory.objects.all(),
        write_only=True,
        source="category",
        required=False,
        allow_null=True,
    )
    category = serializers.StringRelatedField(read_only=True)

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
                Q(created_by=user.id) | Q(is_default=True)
            )
        return fields

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "category",
            "category_id",
            "labour_time",
            "labour_rate",
            "recipes",
            "total_cost",
            "created_by",
        ]
        read_only_fields = ["id", "total_cost"]
        extra_kwargs = {
            "labour_time": {"write_only": True},
            "labour_rate": {"write_only": True},
        }

    def create(self, validated_data):
        return ProductService.create_product(validated_data)

    def update(self, instance, validated_data):
        return ProductService.update_product(instance, validated_data)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if "total_cost" in representation:
            representation["total_cost"] = str(
                Money(representation["total_cost"], self.currency)
            )
        return representation


class ProductListSerializer(serializers.ModelSerializer):
    category = serializers.StringRelatedField(read_only=True)

    @cached_property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

    class Meta:
        model = Product
        fields = ["id", "name", "category", "total_cost", "recipes_count"]
        read_only_fields = fields

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if "total_cost" in representation:
            representation["total_cost"] = str(
                Money(representation["total_cost"], self.currency)
            )
        return representation


class ProductDetailSerializer(serializers.ModelSerializer):
    product_recipes = ProductRecipesSerializer(many=True, read_only=True)
    recipes = serializers.ListField(
        child=RecipeItemSerializer(), min_length=1, write_only=True
    )
    category = ProductCategorySerializer(read_only=True)

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user

        if user and "category_id" in fields:
            fields["category_id"].queryset = fields["category_id"].queryset.filter(
                Q(created_by=user.id) | Q(is_default=True)
            )
        return fields

    class Meta:
        model = Product
        exclude = [
            "created_by",
            "created_at",
            "updated_at",
            "is_active",
        ]
        read_only_fields = [
            "id",
            "product_recipes",
            "recipes_cost",
            "recipes_count",
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
            "recipes_cost",
            "labour_cost",
            "total_cost",
        ]
        for field in money_fields:
            if field in representation:
                amount = representation[field]
                representation[field] = str(Money(amount, self.currency))
        return representation
