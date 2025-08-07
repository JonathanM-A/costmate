from django.db import transaction
from django.db.models import Case, When, DecimalField, F
from django.db.models.functions import Cast
from django.db.models.signals import post_save
from django.db.models import CharField
from .models import Inventory, InventoryHistory
from .signals import update_inventory_values
from ..recipes.signals import update_recipe_inventory_cost


class InventoryUpdateService:
    @classmethod
    def process_inventory_updates(cls, user, entries):
        """
        1. Creates Inventory History Records
        2. Updates Inventory quantities
        3. Manages database transactions
        """
        with transaction.atomic():
            # Disconnect signals temporarily
            post_save.disconnect(
                receiver=update_inventory_values,
                sender=InventoryHistory
            )
            post_save.disconnect(
                receiver=update_recipe_inventory_cost,
                sender=InventoryHistory
            )

            histories, updates = cls._prepare_data(user, entries)

            cls._create_history_records(histories)

            updated_items = cls._update_inventory(user, updates)

            transaction.on_commit(
                lambda: cls._trigger_cost_calculations(histories)
            )

            return updated_items.select_related("inventory_item")

    @staticmethod
    def _prepare_data(user, entries):
        """Structure entries data"""
        histories = []
        updates = {}

        for entry in entries:
            item_id = entry["inventory_item_id"]
            quantity = entry["quantity"]

            histories.append(InventoryHistory(
                inventory_item_id=item_id,
                quantity=quantity,
                supplier_id=entry.get("supplier_id"),
                cost_price=entry.get("cost_price"),
                incident_date=entry.get("incident_date"),
                created_by=user
            ))
            # Aggregating quantities
            updates[item_id] = updates.get(item_id, 0) + quantity

        return histories, updates

    @staticmethod
    def _create_history_records(histories):
        """Bulf create history records"""
        return InventoryHistory.objects.bulk_create(histories)

    @staticmethod
    def _update_inventory(user, updates):
        """Handle all inventory updates"""
        existing = Inventory.objects.filter(
            created_by=user,
            inventory_item_id__in=updates.keys()
        ).select_for_update()

        # Casting UUIDs to str for comparison
        existing_ids = set(
            existing.annotate(
                item_id_str=Cast("inventory_item_id", CharField())
            ).values_list("item_id_str", flat=True)
        )

        # Creating new items
        new_ids = set(updates.keys()) - existing_ids
        if new_ids:
            Inventory.objects.bulk_create([
                Inventory(
                    inventory_item_id=item_id,
                    quantity=updates[item_id],
                    created_by=user
                )
                for item_id in new_ids
            ])

        # Updating existing items using Case statements
        if existing.exists():
            cases = [
                When(inventory_item=item_id, then=F("quantity") + quantity)
                for item_id, quantity in updates.items()
                if item_id in existing_ids
            ]
            Inventory.objects.filter(
                created_by=user, inventory_item_id__in=existing_ids
            ).update(
                quantity=Case(*cases, output_field=DecimalField())
            )
        return Inventory.objects.filter(
            created_by=user,
            inventory_item_id__in=updates.keys()
        )

    @classmethod
    def _trigger_cost_calculations(cls, histories):
        """Reconnect signals and trigger processing"""
        post_save.connect(
                receiver=update_inventory_values, sender=InventoryHistory
            )
        post_save.connect(
            receiver=update_recipe_inventory_cost, sender=InventoryHistory
        )
        for history in histories:
            history.calculate_cost()
