from django.db import transaction
from django.db.models import Case, When, DecimalField, F, Subquery, OuterRef, Max
from django.db.models.functions import Cast
from django.db.models import CharField
from .models import Inventory, InventoryHistory
from ..recipes.services import RecipeService


class InventoryUpdateService:
    @classmethod
    def process_inventory_updates(cls, user, entries):
        """
        1. Creates Inventory History Records
        2. Updates Inventory quantities
        3. Manages database transactions
        """
        with transaction.atomic():

            histories, updates = cls._prepare_data(user, entries)

            cls._create_history_records(histories)

            updated_items = cls._update_inventory(user, updates)

            transaction.on_commit(lambda: cls._cascade_cost_updates(histories, user))

            return updated_items.select_related("inventory_item")

    @classmethod
    def _cascade_cost_updates(cls, histories, user):
        """Update all affected costs"""
        # Calculate cost for InventoryHistory instances
        for history in histories:
            history.calculate_cost()

        # Get unique inventory_items that were updated
        item_ids = {h.inventory_item_id for h in histories}

        # Updating inventory costs
        cls._bulk_update_inventory_costs(item_ids, user)

        # Updating cost for affected Recipes
        RecipeService._bulk_update_recipe_inventory_costs(item_ids, user)


    @staticmethod
    def _prepare_data(user, entries):
        """Structure entries data"""
        histories = []
        updates = {}

        for entry in entries:
            item_id = entry["inventory_item_id"]
            quantity = entry["quantity"]

            histories.append(
                InventoryHistory(
                    inventory_item_id=item_id,
                    quantity=quantity,
                    supplier_id=entry.get("supplier_id"),
                    cost_price=entry.get("cost_price"),
                    incident_date=entry.get("incident_date"),
                    created_by=user,
                )
            )
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
            created_by=user, inventory_item_id__in=updates.keys()
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
            Inventory.objects.bulk_create(
                [
                    Inventory(
                        inventory_item_id=item_id,
                        quantity=updates[item_id],
                        created_by=user,
                    )
                    for item_id in new_ids
                ]
            )

        # Updating existing items using Case statements
        if existing.exists():
            cases = [
                When(inventory_item=item_id, then=F("quantity") + quantity)
                for item_id, quantity in updates.items()
                if item_id in existing_ids
            ]
            Inventory.objects.filter(
                created_by=user, inventory_item_id__in=existing_ids
            ).update(quantity=Case(*cases, output_field=DecimalField()))
        return Inventory.objects.filter(
            created_by=user, inventory_item_id__in=updates.keys()
        )

    @staticmethod
    def _bulk_update_inventory_costs(item_ids, user):
        # Get the Max cost_per_unit from last two inventory additions
        last_two_costs = InventoryHistory.objects.filter(
            inventory_item=OuterRef("inventory_item_id"),
            is_addition=True,
            created_by=user,
        ).order_by("-incident_date", "-created_at")[:2]

        # Update the costs directly in the db in one query
        return (
            Inventory.objects.filter(inventory_item_id__in=item_ids, created_by=user)
            .annotate(
                recent_max_cost=Subquery(
                    last_two_costs.values("cost_per_unit")
                    .annotate(max_cost=Max("cost_per_unit"))
                    .values("max_cost")[:1]
                )
            )
            .update(
                cost_per_unit=F("recent_max_cost"),
                total_value=F("quantity") * F("recent_max_cost"),
            )
        )
