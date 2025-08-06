from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import InventoryHistory


@receiver(post_save, sender=InventoryHistory)
def update_inventory_values(sender, instance, **kwargs):
    """
    Update the total value and cost per unit of the inventory item after saving an InventoryHistory instance.
    """
    inventory_entry = instance.inventory_item.inventory.filter(
        created_by=instance.created_by
    ).first()
    if not inventory_entry:
        return
    inventory_entry.save()  # Ensure the inventory entry is saved to update costs
