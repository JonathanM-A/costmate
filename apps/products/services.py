from decimal import Decimal
from django.db import transaction
from .models import Product, ProductRecipes
from apps.users.utils import get_user_preferrence_from_cache


class ProductService:
    @classmethod
    def create_product(cls, validated_data):
        recipes = validated_data.pop("recipes")

        user = validated_data.get("created_by")

        # Set defaults
        validated_data.setdefault(
            "labour_rate",
            get_user_preferrence_from_cache(user.id, "labour_rate", 20.00),
        )

        with transaction.atomic():
            product = Product.objects.create(**validated_data)
            cls._bulk_create_product_recipes(product, recipes, user)
            product.refresh_from_db()
            product.save()
            return product

    @classmethod
    def update_product(cls, instance, validated_data):
        recipes = validated_data.pop("recipes", None)

        with transaction.atomic():
            update_fields = []
            for field, value in validated_data.items():
                setattr(instance, field, value)
                update_fields.append(field)

            if update_fields:
                instance.save(update_fields=update_fields)

            if recipes is not None:
                cls._bulk_replace_product_recipes(instance, recipes)
                instance.refresh_from_db()
                instance.save()

            return instance

    @staticmethod
    def _bulk_create_product_recipes(product, recipes, user):
        product_recipes = ProductRecipes.objects.bulk_create([
            ProductRecipes(
                product=product,
                recipe_id=recipe["recipe_id"],
                quantity=recipe["quantity"],
                cost=Decimal("0.00"),
                created_by=user,
            )
            for recipe in recipes
        ])

        # Calculate costs for each ProductRecipes
        for pr in product_recipes:
            pr.calculate_cost()
            pr.save(update_fields=["cost"])

        return product_recipes

    @staticmethod
    def _bulk_replace_product_recipes(product, recipes):
        ProductRecipes.objects.filter(product=product).delete()

        product_recipes = ProductRecipes.objects.bulk_create([
            ProductRecipes(
                product=product,
                recipe_id=recipe["recipe_id"],
                quantity=recipe["quantity"],
                cost=Decimal("0.00"),
                created_by=product.created_by,
            )
            for recipe in recipes
        ])

        # Calculate costs for each ProductRecipes
        for pr in product_recipes:
            pr.calculate_cost()
            pr.save(update_fields=["cost"])

        return product_recipes

    @classmethod
    def recalculate_products_for_recipe(cls, recipe_id):
        """
        Recalculate costs for all products that contain the given recipe.
        Should be called whenever a recipe's total_cost changes.
        """
        with transaction.atomic():
            # Get all ProductRecipes for this recipe
            product_recipes = ProductRecipes.objects.filter(recipe_id=recipe_id)

            # Recalculate cost for each ProductRecipes
            for pr in product_recipes:
                pr.calculate_cost()
                pr.save(update_fields=["cost"])

            # Get affected products and recalculate their total costs
            affected_product_ids = list(product_recipes.values_list("product_id", flat=True).distinct())
            for product in Product.objects.filter(id__in=affected_product_ids):
                product.calculate_costs()
                product.save(update_fields=["recipes_cost", "total_cost"])
