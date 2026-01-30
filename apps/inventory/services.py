from decimal import Decimal
from django.db import transaction
from django.db.models import Case, When, DecimalField, F, Subquery, OuterRef, Max
from django.db.models.functions import Cast
from django.db.models import CharField
from .models import Inventory, InventoryHistory, InventoryItem, Supplier
import logging

logger = logging.Logger(__name__)


class InventoryUpdateService:
    @classmethod
    def process_inventory_updates(cls, user, entries):
        """
        1. Creates Inventory History Records
        2. Updates Inventory quantities
        3. Manages database transactions
        """
        with transaction.atomic():

            histories, updates, suppliers_totals = cls._prepare_data(user, entries)

            cls._create_history_records(histories)

            cls._update_supplier_total_spent(suppliers_totals)

            updated_items = cls._update_inventory(user, updates)

            transaction.on_commit(lambda: cls._cascade_cost_updates(histories, user))

            return histories

    @classmethod
    def _cascade_cost_updates(cls, histories, user):
        """Update all affected costs"""
        from ..recipes.services import RecipeService

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
        suppliers_totals = {}
        updates = {}

        for entry in entries:
            item_id = entry["inventory_item_id"]
            quantity = entry["quantity"]
            unit = entry.get("unit", None)

            inventory_item_unit = (
                InventoryItem.objects.filter(id=item_id)
                .values_list("unit", flat=True)
                .first()
            )

            if unit:
                if InventoryUnitService.validate_unit_compatibility(inventory_item_unit, unit):
                    converted_quantity = InventoryUnitService.convert_quantity(
                        inventory_item_unit, unit, quantity
                    )
                    quantity = converted_quantity
            histories.append(
                InventoryHistory(
                    inventory_item_id=item_id,
                    quantity=quantity,
                    supplier_id=entry.get("supplier_id"),
                    cost_price=entry.get("cost_price"),
                    incident_date=entry.get("incident_date"),
                    created_by=user,
                    cost_per_unit=(
                        Decimal(entry.get("cost_price", 0)) / Decimal(quantity)
                        if quantity > 0
                        else Decimal(0)
                    ),
                )
            )
            # Aggregating quantities
            updates[item_id] = updates.get(item_id, 0) + quantity

            # Aggregating supplier totals
            supplier_id = entry.get("supplier_id")
            cost_price = entry.get("cost_price", 0)
            if supplier_id:
                suppliers_totals.setdefault(supplier_id, 0)
                suppliers_totals[supplier_id] += cost_price

        return histories, updates, suppliers_totals

    @staticmethod
    def _create_history_records(histories):
        """Bulf create history records"""
        return InventoryHistory.objects.bulk_create(histories)

    @classmethod
    def _update_supplier_total_spent(cls, supplier_totals):
        from .models import Supplier  # Importing here to avoid circular imports

        """Update total spent for suppliers involved in the histories"""
        suppliers = Supplier.objects.filter(
            id__in=supplier_totals.keys()
        ).select_for_update()

        suppliers_total_spent = {str(s.id): s.total_spent for s in suppliers}

        for supplier in suppliers:
            additional_spent = supplier_totals.get(str(supplier.id))
            supplier.total_spent = (
                suppliers_total_spent[str(supplier.id)] + Decimal(additional_spent)
            )
        
        Supplier.objects.bulk_update(suppliers, ["total_spent"])

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


class UnitMismatchError(Exception):
    """Custom exception for unit mismatches."""

    pass


class InventoryUnitService:

    CONVERSION_MAP = {
        # Mass (Base: g)
        "g": {"factor": 1.0, "type": "mass"},
        "kg": {"factor": 1000.0, "type": "mass"},
        "oz": {"factor": 28.3495, "type": "mass"},
        "lb": {"factor": 453.592, "type": "mass"},
        # Volume (Base: mL)
        "ml": {"factor": 1.0, "type": "volume"},
        "l": {"factor": 1000.0, "type": "volume"},
        "fl oz": {"factor": 29.5735, "type": "volume"},
        "cup": {"factor": 240.0, "type": "volume"},
        "tsp": {"factor": 4.92892, "type": "volume"},
        "tbsp": {"factor": 14.7868, "type": "volume"},
        "pt": {"factor": 473.176, "type": "volume"},
        "qt": {"factor": 946.353, "type": "volume"},
        "gal": {"factor": 3785.41, "type": "volume"},
    }

    @classmethod
    def validate_unit_compatibility(cls, inventory_item_unit, unit):
        """Validate if inventory item unit is compatible with recipe unit."""

        item_unit = cls.CONVERSION_MAP.get(inventory_item_unit.lower())
        payload_unit = cls.CONVERSION_MAP.get(unit.lower())

        if not item_unit or not payload_unit:
            # If either unit is not in the conversion map, assume they are compatible (e.g., "pcs", "bottle")
            return

        if item_unit["type"] != payload_unit["type"]:
            logger.error(f"Unit mismatch: {inventory_item_unit} vs {unit}")
            raise UnitMismatchError(
                f"Unit mismatch: Inventory item unit '{inventory_item_unit}' "
                f"is not compatible with recipe unit '{unit}'."
            )

        # Units are compatible
        return True

    @classmethod
    def convert_quantity(cls, inventory_item_unit, unit, quantity):
        """Convert quantity from recipe unit to inventory item unit."""

        if inventory_item_unit.lower() == unit.lower():
            return quantity

        item_factor = Decimal(cls.CONVERSION_MAP.get(inventory_item_unit.lower()).get("factor")) # type: ignore
        payload_factor = Decimal(cls.CONVERSION_MAP.get(unit.lower()).get("factor")) # type: ignore

        if item_factor and payload_factor:
            # Convert quantity to base unit, then to inventory item unit
            base_quantity = Decimal(quantity) * payload_factor
            converted_quantity = base_quantity / item_factor
            return converted_quantity

        # If either unit is not in the conversion map, return original quantity
        return quantity
