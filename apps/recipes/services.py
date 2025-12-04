from django.db import transaction
from django.db.models import OuterRef, Subquery, F, Sum, Value
from django.db.models.functions import Coalesce
from decimal import Decimal
from .models import Recipe, RecipeInventory
from ..inventory.models import Inventory
from ..users.utils import get_user_preferrence_from_cache


class RecipeService:
    @classmethod
    def create_recipe(cls, user, validated_data):
        ingredients = validated_data.pop("ingredients")

        # Set defaults
        validated_data.setdefault(
            "profit_margin",
            get_user_preferrence_from_cache(user.id, "profit_margin", 30.00),
        )
        validated_data.setdefault(
            "profit_margin", get_user_preferrence_from_cache(user.id, "labour_rate", 20.00)
        )

        with transaction.atomic():
            # Creating recipe
            recipe = Recipe.objects.create(created_by=user, **validated_data)

            # Creating RecipeInventory
            recipe_inventories = cls._bulk_create_ingredients(recipe, ingredients)

            RecipeInventory.objects.filter()

            item_ids = set()

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
            return instance

    @staticmethod
    def _bulk_create_ingredients(recipe, ingredients):
        """Create all recipe ingredients"""
        recipe_inventories = RecipeInventory.objects.bulk_create(
            [
                RecipeInventory(
                    recipe=recipe,
                    inventory_item_id=ing["inventory_item_id"],
                    quantity=ing["quantity"],
                    cost=Decimal("0.00"),
                )
                for ing in ingredients
            ]
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
                cost_price=(
                    F("inventory_items_cost")
                    + F("labour_cost")
                    + F("packaging_cost")
                    + F("overhead_cost")
                ),
                selling_price=(
                    (
                        F("inventory_items_cost")
                        + F("labour_cost")
                        + F("packaging_cost")
                        + F("overhead_cost")
                    )
                    * (1 + (F("profit_margin") / Decimal("100.00")))
                ),
            )
            
