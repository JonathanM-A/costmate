from djmoney.money import Money
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from ..users.utils import get_user_preferrence_from_cache
from ..users.serializers import UserFormattedDate
from .models import Order, Customer, Recipe, OrderRecipe, Overhead


class CustomerOrderRecipeSerializer(serializers.ModelSerializer):
    """Lightweight serializer for recipe names in customer order history."""
    recipe_name = serializers.StringRelatedField(read_only=True, source="recipe")

    class Meta:
        model = OrderRecipe
        fields = ["recipe_name"]


class CustomerOrderSerializer(serializers.ModelSerializer):
    """Lightweight serializer for customer order history display."""
    recipes = serializers.SerializerMethodField()
    delivery_date = UserFormattedDate(read_only=True)
    suggested_price = serializers.SerializerMethodField()
    preferred_final_price = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["id", "order_no", "recipes", "suggested_price", "preferred_final_price", "delivery_date", "status"]
        read_only_fields = fields

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

    def get_recipes(self, obj):
        order_recipes = getattr(obj, "prefetched_order_recipes", None) or obj.order_recipes.all()
        return [or_.recipe.name for or_ in order_recipes]

    def get_suggested_price(self, obj):
        return str(Money(obj.suggested_price, self.currency))

    def get_preferred_final_price(self, obj):
        if obj.preferred_final_price is not None:
            return str(Money(obj.preferred_final_price, self.currency))
        return None


class OrderRecipeSerializer(serializers.ModelSerializer):
    recipe_id = serializers.PrimaryKeyRelatedField(
        queryset=Recipe.objects.all(), write_only=True, source="recipe"
    )
    recipe_name = serializers.StringRelatedField(read_only=True, source="recipe")

    class Meta:
        model = OrderRecipe
        exclude = ["order"]
        read_only_fields = ["id", "line_cost", "order"]

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

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

        if "line_cost" in representation:
            representation["line_cost"] = str(Money(representation["line_cost"], self.currency))

        return representation


class OrderSerializer(serializers.ModelSerializer):
    recipes = serializers.ListField(
        child=serializers.DictField(), min_length=1, write_only=True
    )
    order_recipes = OrderRecipeSerializer(many=True, read_only=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    delivery_date = UserFormattedDate(allow_null=True, required=False)

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
            "subtotal",
            "total_cost",
            "order_price",
            "final_price",
            "vat_amount",
            "suggested_price",
        ]
        extra_kwargs = {
            "delivery_date": {"required": False, "allow_null": True},
            "overhead": {"required": False},
            "overhead_is_percentage": {"required": False},
            "packaging": {"required": False},
            "packaging_is_percentage": {"required": False},
            "discount": {"required": False},
            "discount_is_percentage": {"required": False},
            "profit_margin": {"required": False},
            "preferred_final_price": {"required": False, "allow_null": True},
        }

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user

        if user and "customer" in fields:
            fields["customer"].queryset = fields["customer"].queryset.filter(
                Q(is_active=True) | Q(created_by=user.id)
            )
        return fields


    def create(self, validated_data):
        from ..notifications.models import Notification
        from django.contrib.contenttypes.models import ContentType

        recipes = validated_data.pop("recipes")
        user = self.context["request"].user
        validated_data["created_by"] = user

        with transaction.atomic():
            order_instance = Order.objects.create(**validated_data)

            # Prefetch all recipes in one query to avoid N+1
            recipe_ids = [recipe_data["recipe_id"] for recipe_data in recipes]
            recipe_map = {
                str(recipe_obj.id): recipe_obj
                for recipe_obj in Recipe.objects.filter(id__in=recipe_ids)
            }

            order_recipes = [
                OrderRecipe(
                    order=order_instance,
                    recipe_id=recipe_data["recipe_id"],
                    quantity=recipe_data.get("quantity", 1),
                    line_cost=recipe_map[recipe_data["recipe_id"]].total_cost * recipe_data.get("quantity", 1),
                )
                for recipe_data in recipes
            ]
            OrderRecipe.objects.bulk_create(order_recipes)
            order_instance.save()

            # Check inventory availability and create notification if insufficient
            is_available, insufficient_items = order_instance.check_inventory_availability()
            if not is_available:
                message = f"Order {order_instance.order_no} created but insufficient inventory for:\n"
                for item in insufficient_items:
                    message += f"- {item['recipe']}: {item['ingredient']} (Need: {item['needed']}{item['unit']}, Available: {item['available']}{item['unit']})\n"

                Notification.objects.create(
                    user=user,
                    notification_type="INSUFFICIENT_INVENTORY",
                    message=message,
                    content_type=ContentType.objects.get_for_model(Order),
                    object_id=order_instance.id,
                )

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

                # Prefetch all recipes in one query to avoid N+1
                recipe_ids = [recipe_data["recipe_id"] for recipe_data in recipes]
                recipe_map = {
                    str(recipe_obj.id): recipe_obj
                    for recipe_obj in Recipe.objects.filter(id__in=recipe_ids)
                }

                new_recipes = [
                    OrderRecipe(
                        order=instance,
                        recipe_id=recipe_data["recipe_id"],
                        quantity=recipe_data.get("quantity", 1),
                        line_cost=recipe_map[recipe_data["recipe_id"]].total_cost * recipe_data.get("quantity", 1),
                    )
                    for recipe_data in recipes
                ]
                OrderRecipe.objects.bulk_create(new_recipes)

                # Remove recipes that are no longer in the new list
                if existing_recipes:
                    OrderRecipe.objects.filter(id__in=existing_recipes).delete()

                instance.save()

        return instance

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        money_fields = [
            "subtotal",
            "overhead",
            "packaging",
            "total_cost",
            "order_price",
            "discount",
            "final_price",
            "vat_amount",
            "suggested_price",
            "preferred_final_price",
        ]

        for field in money_fields:
            if field in representation and representation[field] is not None:
                representation[field] = str(Money(amount=representation[field], currency=self.currency))

        representation["profit_margin"] = str(instance.profit_margin) + "%"
        representation["vat_rate"] = str(instance.vat_rate) + "%"
        representation["customer"] = instance.customer.name
        return representation

class OverheadSerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Overhead
        exclude = ["is_active", "created_at", "updated_at"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        return value.title()

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["yearly_cost"] = str(
            Money(amount=instance.yearly_cost, currency=self.currency)
        )
        representation["monthly_cost"] = str(
            Money(amount=instance.monthly_cost, currency=self.currency)
        )
        return representation


class OverheadUpdateItemSerializer(serializers.Serializer):
    id = serializers.PrimaryKeyRelatedField(queryset=Overhead.objects.all())
    monthly_cost = serializers.DecimalField(max_digits=10, decimal_places=2)
    yearly_cost = serializers.DecimalField(max_digits=10, decimal_places=2)

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user
        if user and "id" in fields:
            fields["id"].queryset = fields["id"].queryset.filter(created_by=user)
        return fields


class BulkOverheadUpdateSerializer(serializers.Serializer):
    overheads = OverheadUpdateItemSerializer(many=True)

    def update(self, instance, validated_data):
        overheads_data = validated_data["overheads"]

        updated_overheads = []
        for item in overheads_data:
            overhead = item["id"]
            overhead.monthly_cost = item["monthly_cost"]
            overhead.yearly_cost = item["yearly_cost"]
            updated_overheads.append(overhead)

        with transaction.atomic():
            Overhead.objects.bulk_update(
                updated_overheads, ["monthly_cost", "yearly_cost"]
            )

        return updated_overheads