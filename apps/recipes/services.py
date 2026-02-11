from django.db import transaction
from django.db.models import (
    OuterRef,
    Subquery,
    F,
    Sum,
    Value,
    Q,
)
from django.db.models.functions import Coalesce
from decimal import Decimal
from .models import Recipe, RecipeInventory
from ..inventory.models import Inventory, InventoryItem
from ..inventory.services import InventoryUnitService
from ..users.utils import get_user_preferrence_from_cache
from ..products.services import ProductService


class RecipeService:
    @classmethod
    def create_recipe(cls, user, validated_data):
        ingredients = validated_data.pop("ingredients")

        # Set defaults
        validated_data.setdefault(
            "labour_rate",
            get_user_preferrence_from_cache(user.id, "labour_rate", 20.00),
        )

        with transaction.atomic():
            # Creating recipe
            recipe = Recipe.objects.create(created_by=user, **validated_data)

            # Creating RecipeInventory
            recipe_inventories = cls._bulk_create_ingredients(recipe, ingredients)

            item_ids = {ri.inventory_item for ri in recipe_inventories}

            # Calculating costs for RecipeInventory
            cls._bulk_update_recipe_inventory_costs(item_ids, user)

            recipe.refresh_from_db()
            recipe.calculate_cost()
            return recipe

    @classmethod
    def update_recipe(cls, instance, validated_data):
        ingredients = validated_data.pop("ingredients", None)

        with transaction.atomic():
            # Update recipe
            update_fields = []
            for field, value in validated_data.items():
                setattr(instance, field, value)
                update_fields.append(field)
            instance.save(update_fields=update_fields)

            if ingredients is not None:
                recipe_inventories = cls._bulk_replace_ingredients(
                    instance, ingredients
                )

                item_ids = {ri.inventory_item.id for ri in recipe_inventories}

                cls._bulk_update_recipe_inventory_costs(
                    item_ids, user=instance.created_by
                )

                instance.refresh_from_db()
                instance.calculate_cost()

            # Recalculate costs for products that use this recipe
            ProductService.recalculate_products_for_recipe(instance.id)

            return instance

    @staticmethod
    def _bulk_create_ingredients(recipe, ingredients):
        """Create all recipe ingredients"""

        uncreated_recipe_inventories = []

        for  ing in ingredients:
            quantity = ing["quantity"]
            unit = ing.get("unit")

            inventory_item_unit = InventoryItem.objects.filter(id=ing["inventory_item_id"]).values_list("unit", flat=True).first()
            if unit:
                InventoryUnitService.validate_unit_compatibility(
                    inventory_item_unit, unit
                )
                converted_quantity = InventoryUnitService.convert_quantity(
                    inventory_item_unit, unit, quantity
                )
                quantity = converted_quantity
            uncreated_recipe_inventories.append(
                RecipeInventory(
                    recipe=recipe,
                    inventory_item_id=ing["inventory_item_id"],
                    quantity=quantity,
                    cost=Decimal("0.00"),
                    suggested_cost=ing.get("suggested_cost", Decimal("0.00")),
                )
            )

        recipe_inventories = RecipeInventory.objects.bulk_create(
            uncreated_recipe_inventories
        )
        
        return recipe_inventories

    @staticmethod
    def _bulk_replace_ingredients(recipe, ingredients):
        """Atomically replace all ingredients"""
        RecipeInventory.objects.filter(recipe=recipe).delete()

        recipe_inventories = RecipeInventory.objects.bulk_create(
            [
                RecipeInventory(
                    recipe=recipe,
                    inventory_item_id=ing["inventory_item_id"],
                    quantity=ing["quantity"],
                    cost=Decimal("0.00"),
                    suggested_cost=ing.get("suggested_cost", Decimal("0.00")),
                )
                for ing in ingredients
            ]
        )
        return recipe_inventories

    @staticmethod
    def _bulk_update_recipe_inventory_costs(item_ids, user):

        inventories = Inventory.objects.filter(
            created_by=user, inventory_item=OuterRef("inventory_item_id")
        )

        ris = RecipeInventory.objects.filter(
            inventory_item_id__in=item_ids, recipe__created_by=user
        )

        # Use Coalesce to default cost_per_unit to 0 when the Subquery returns NULL
        cost_subquery = Subquery(inventories.values("cost_per_unit")[:1])
        ris.update(cost=F("quantity") * Coalesce(cost_subquery, Value(Decimal("0.00"))))

        updated = ris.filter(Q(cost=Decimal("0.00")) & Q(suggested_cost__gt=Decimal("0.00"))).update(
            cost=F("suggested_cost")
        )
        

        affected_recipe_ids = list(ris.values_list("recipe_id", flat=True).distinct())

        if affected_recipe_ids:
            Recipe.objects.filter(id__in=affected_recipe_ids).update(
                inventory_items_cost=Subquery(
                    RecipeInventory.objects.filter(recipe_id=OuterRef("id"))
                    .values("recipe_id")
                    .annotate(sum_cost=Sum("cost"))
                    .values("sum_cost")[:1]
                ),
            )

            Recipe.objects.filter(id__in=affected_recipe_ids).update(
                total_cost=F("inventory_items_cost") + F("labour_cost")
            )

            for recipe_id in affected_recipe_ids:
                ProductService.recalculate_products_for_recipe(recipe_id)
