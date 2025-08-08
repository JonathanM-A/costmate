from django.db.models.signals import post_save
from django.dispatch import receiver
from ..inventory.models import Inventory
from .models import RecipeInventory


# @receiver(post_save, sender=Inventory)
# def update_recipe_inventory_cost(sender, instance, **kwargs):
#     """
#     Update the cost of the RecipeInventory item based on the latest Inventory.
#     """
#     inventory_item = instance.inventory_item
#     recipe_inventories = inventory_item.recipe_inventory.all()
#     for ri in recipe_inventories:
#         ri.calculate_cost()
