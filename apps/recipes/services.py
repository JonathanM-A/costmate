from django.db import transaction
from .models import Recipe, RecipeInventory
from ..users.utils import get_user_preferrence_from_cache


class RecipeService:
    @classmethod
    def create_recipe(cls, user, validated_data):
        ingredients = validated_data.pop("ingredients")

        # Set defaults
        validated_data.setdefault(
            "profit_margin",
            get_user_preferrence_from_cache(user, "profit_margin", 30.00)
        )
        validated_data.setdefault(
            "profit_margin",
            get_user_preferrence_from_cache(user, "labour_rate", 20.00)
        )
        
        with transaction.atomic():
            # Creating recipe
            recipe = Recipe.objects.create(
                created_by=user,
                **validated_data
            )

            # Creating RecipeInventory
            cls._bulk_create_ingredients(recipe, user, ingredients)

            # Calculating costs
            transaction.on_commit(
                lambda: recipe.calculate_cost()
            )
            
            return recipe

    @classmethod
    def update_recipe(cls, instance, validated_data):
        ingredients = validated_data.pop("ingredients", None)

        with transaction.atomic():
            # Update recipe
            recipe = super().update(instance, validated_data)

            if ingredients is not None:
                cls._bulk_replace_ingredients(recipe, ingredients)
            
            transaction.on_commit(
                lambda: recipe.calculate_cost()
            )

            return recipe


    @staticmethod
    def _bulk_create_ingredients(recipe, user, ingredients):
        """Create all recipe ingredients"""
        RecipeInventory.objects.bulk_create(
            [
                RecipeInventory(
                    recipe=recipe,
                    inventory_item_id=ing["inventory_item_id"],
                    quantity=ing["quantity"],
                    created_by=user
                ) for ing in ingredients
            ]
        )

    @staticmethod
    def _bulk_replace_ingredients(recipe, ingredients):
        """Atomically replace all ingredients"""
        RecipeInventory.objects.filter(recipe=recipe).delete()

        RecipeInventory.objects.bulk_create(
            [
                RecipeInventory(
                    recipe=recipe,
                    inventory_item_id=ing["inventory_item_id"],
                    quantity=ing["quantity"],
                    created_by=recipe.created_by
                )
                for ing in ingredients
            ]
        )
