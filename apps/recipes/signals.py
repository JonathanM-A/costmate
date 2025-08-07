from django.db.models.signals import post_save
from django.dispatch import receiver
from ..inventory.models import InventoryHistory
from .models import RecipeInventory


@receiver(post_save, sender=InventoryHistory)
def update_recipe_inventory_cost(sender, instance, **kwargs):
    """
    Update the cost of the RecipeInventory item based on the latest InventoryHistory.
    """
    if instance.is_addition:
        recipe_inventories = RecipeInventory.objects.filter(
            inventory_item=instance.inventory_item
        )
        if recipe_inventories.exists():
            for recipe_inventory in recipe_inventories:
                recipe_inventory.save()  # This will call the overridden save method which calculates the cost
