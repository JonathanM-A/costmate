from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from djmoney.money import Money
from ..users.utils import get_user_preferrence_from_cache
from .models import Order, Customer, Recipe, OrderRecipe


class OrderRecipeSerializer(serializers.ModelSerializer):
    recipe_id = serializers.PrimaryKeyRelatedField(
        queryset=Recipe.objects.all(), write_only=True
    )
    recipe = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = OrderRecipe
        exclude = ["order"]
        read_only_fields = ["id", "line_value", "order"]

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user

        if user and "recipe_id" in fields:
            fields["recipe_id"].queryset = fields["recipe_id"].queryset.filter(
                Q(is_active=True) | Q(created_by=user.id)
            )
        return fields

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["line_value"] = str(
            Money(
                amount=instance.line_value,
                currency=get_user_preferrence_from_cache(
                    self.context["request"].user, "currency", "USD"
                ),
            )
        )
        return representation


class OrderSerializer(serializers.ModelSerializer):
    recipes = serializers.ListField(
        child=serializers.DictField(), min_length=1, write_only=True
    )
    order_recipes = OrderRecipeSerializer(many=True, read_only=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())

    class Meta:
        model = Order
        exclude = ["created_at", "updated_at", "created_by", "is_active"]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "status",
            "order_no",
            "total_value",
            "profit",
            "profit_percentage",
        ]
        extra_kwargs = {
            "delivery_date": {"required": False, "allow_null": True},
        }


    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user

        if user and "customer" in fields:
            fields["customer"].queryset = fields["customer"].queryset.filter(
                Q(is_active=True) | Q(created_by=user.id)
            )
        return fields

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        currency = get_user_preferrence_from_cache(
            self.context["request"].user, "currency", "USD"
        )
        representation["total_value"] = str(
            Money(amount=instance.total_value, currency=currency)
        )
        representation["profit"] = str(Money(amount=instance.profit, currency=currency))
        representation["profit_percentage"] = str(instance.profit_percentage) + "%"
        return representation

    def create(self, validated_data):
        recipes = validated_data.pop("recipes")
        validated_data["created_by"] = self.context["request"].user

        with transaction.atomic():
            order_instance = Order.objects.create(**validated_data)

            order_recipes = [
                OrderRecipe(
                    order=order_instance,
                    recipe_id=recipe["recipe_id"],
                    quantity=recipe.get("quantity", 1),
                )
                for recipe in recipes
            ]
            OrderRecipe.objects.bulk_create(order_recipes)
            order_instance.save()
            return order_instance

    def update(self, instance, validated_data):
        recipes = validated_data.pop("recipes", None)
        validated_data["created_by"] = self.context["request"].user

        with transaction.atomic():
            instance = super().update(instance, validated_data)

            if recipes is not None:
                existing_recipes = set(
                    instance.order_recipes.values_list("id", flat=True)
                )
                new_recipes = []

                for recipe in recipes:
                    new_recipes.append(
                        OrderRecipe(
                            order=instance,
                            recipe_id=recipe["recipe_id"],
                            quantity=recipe.get("quantity", 1),
                        )
                    )
                OrderRecipe.objects.bulk_create(new_recipes)

                # Remove recipes that are no longer in the new list
                if existing_recipes:
                    OrderRecipe.objects.filter(id__in=existing_recipes).delete()

                instance.save()

        return instance
