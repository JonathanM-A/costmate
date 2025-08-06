from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from .models import Order, Customer, Recipe, OrderRecipe
from ..recipes.serializers import RecipeSerializer


class OrderRecipeSerializer(serializers.ModelSerializer):
    recipe_id = serializers.PrimaryKeyRelatedField(
        queryset=Recipe.objects.all(), write_only=True
    )
    recipe = RecipeSerializer(read_only=True)

    class Meta:
        model = OrderRecipe
        fields = "__all__"
        read_only_fields = ["id", "line_value", "order"]

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user

        if user and "recipe_id" in fields:
            fields["recipe_id"].queryset = fields["recipe_id"].queryset.filter(
                Q(is_active=True) | Q(created_by=user.id)
            )
        return fields


class OrderRecipesSerializer(serializers.Serializer):
    order_recipes = OrderRecipeSerializer(many=True, write_only=True)
    quantity = serializers.IntegerField(min_value=1, default=1, write_only=True)


class OrderSerializer(serializers.ModelSerializer):
    recipes = serializers.ListField(
        child=serializers.DictField(), min_length=1, write_only=True
    )
    order_recipes = OrderRecipeSerializer(many=True, read_only=True)
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), write_only=True
    )

    class Meta:
        model = Order
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "status", "order_no"]

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user

        if user and "customer" in fields:
            fields["customer"].queryset = fields["customer"].queryset.filter(
                Q(is_active=True) | Q(created_by=user.id)
            )
        return fields

    def create(self, validated_data):
        recipes = validated_data.pop("recipes")
        validated_data["created_by"] = self.context["request"].user

        with transaction.atomic():
            order_instance = Order.objects.create(**validated_data)

            for recipe in recipes:
                OrderRecipe.objects.create(
                    order=order_instance,
                    recipe_id=recipe["recipe_id"],
                    quantity=recipe.get("quantity", 1),
                )

            order_instance.calculate_total_value()
            order_instance.save()

            return order_instance

    def update(self, instance, validated_data):
        recipes = validated_data.pop("recipes", None)
        validated_data["created_by"] = self.context["request"].user

        with transaction.atomic():
            instance = super().update(instance, validated_data)

            if recipes is not None:
                instance.recipes.all().delete()  # Clear existing recipes

                for recipe in recipes:
                    recipe["order_id"] = instance.id
                    serializer = OrderRecipeSerializer(
                        data=recipe, context=self.context
                    )
                    serializer.is_valid(raise_exception=True)
                    serializer.save()

                instance.refresh_from_db()
                instance.calculate_total_value()
                instance.save()

        return instance
