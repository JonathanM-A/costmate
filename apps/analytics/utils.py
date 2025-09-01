from django.db.models import Sum, F, Q, DecimalField
from django.db.models.functions import Coalesce
from djmoney.money import Money
from ..inventory.models import InventoryItem, Inventory, InventoryHistory
from ..orders.models import OrderRecipe


def calculate_inventory_turnover(user, start_date=None, end_date=None, currency="USD"):
    # Get current inventory status in bulk
    current_inventory = (
        Inventory.objects.filter(created_by=user)
        .select_related("inventory_item")
        .values("inventory_item_id", "quantity", "cost_per_unit")
    )

    current_inventory_dict = {
        item["inventory_item_id"]: {
            "quantity": item["quantity"] or 0,
            "cost_per_unit": item["cost_per_unit"] or 0,
        }
        for item in current_inventory
    }

    # Get all inventory items for this user
    inventory_items = InventoryItem.objects.filter(
        Q(created_by=user) | Q(is_default=True)
    )

    # Calculate consumption from orders in bulk
    # Consumption after start_date
    start_consumption = {}
    if start_date:
        consumption_data = (
            OrderRecipe.objects.filter(
                order__created_by=user,
                order__status="completed",
                order__created_at__gte=start_date,
            )
            .values("recipe__ingredients__inventory_item_id")
            .annotate(
                total_consumed=Coalesce(
                    Sum(F("recipe__ingredients__quantity") * F("quantity")),
                    0,
                    output_field=DecimalField(),
                )
            )
        )

        start_consumption = {
            item["recipe__ingredients__inventory_item_id"]: item["total_consumed"]
            for item in consumption_data
        }

    # Calculate consumption after end_date
    end_consumption = {}
    if end_date:
        consumption_data = (
            OrderRecipe.objects.filter(
                order__created_by=user,
                order__status="completed",
                order__created_at__gte=end_date,
            )
            .values("recipe__ingredients__inventory_item_id")
            .annotate(
                total_consumed=Coalesce(
                    Sum(F("recipe__ingredients__quantity") * F("quantity")),
                    0,
                    output_field=DecimalField(),
                )
            )
        )

        end_consumption = {
            item["recipe__ingredients__inventory_item_id"]: item["total_consumed"]
            for item in consumption_data
        }

    # Calculate inventory additions in bulk
    start_additions = {}
    if start_date:
        additions_data = (
            InventoryHistory.objects.filter(
                created_by=user, is_addition=True, incident_date__gte=start_date
            )
            .values("inventory_item_id")
            .annotate(
                total_added=Coalesce(Sum("quantity"), 0, output_field=DecimalField())
            )
        )

        start_additions = {
            item["inventory_item_id"]: item["total_added"] for item in additions_data
        }

    end_additions = {}
    if end_date:
        additions_data = (
            InventoryHistory.objects.filter(
                created_by=user, is_addition=True, incident_date__gte=end_date
            )
            .values("inventory_item_id")
            .annotate(
                total_added=Coalesce(Sum("quantity"), 0, output_field=DecimalField())
            )
        )

        end_additions = {
            item["inventory_item_id"]: item["total_added"] for item in additions_data
        }

    # Calculate COGS for the period in bulk
    cogs_data = {}
    if start_date and end_date:
        cogs_calculations = (
            OrderRecipe.objects.filter(
                order__created_by=user,
                order__status="completed",
                order__created_at__gte=start_date,
                order__created_at__lte=end_date,
            )
            .values("recipe__ingredients__inventory_item_id")
            .annotate(
                total_cogs=Coalesce(
                    Sum(F("recipe__ingredients__cost") * F("quantity")),
                    0,
                    output_field=DecimalField(),
                )
            )
        )

        cogs_data = {
            item["recipe__ingredients__inventory_item_id"]: item["total_cogs"]
            for item in cogs_calculations
        }

    # Calculate turnover for all items
    turnover_results = []

    for item in inventory_items:
        item_id = item.id
        current_data = current_inventory_dict.get(
            item_id, {"quantity": 0, "cost_per_unit": 0}
        )
        current_qty = current_data["quantity"]
        current_cost = current_data["cost_per_unit"]

        # Calculate start quantity
        start_qty = current_qty
        if start_date:
            consumed = start_consumption.get(item_id, 0)
            added = start_additions.get(item_id, 0)
            start_qty += consumed - added

        # Calculate end quantity
        end_qty = current_qty
        if end_date:
            consumed = end_consumption.get(item_id, 0)
            added = end_additions.get(item_id, 0)
            end_qty += consumed - added

        # Calculate values and turnover
        start_value = start_qty * current_cost
        end_value = end_qty * current_cost
        avg_inventory_value = (start_value + end_value) / 2

        cogs = cogs_data.get(item_id, 0) if start_date and end_date else 0
        turnover_ratio = cogs / avg_inventory_value if avg_inventory_value > 0 else 0

        turnover_results.append(
            {
                "item_name": item.name,
                "turnover_ratio": round(turnover_ratio, 2),
                "cogs": str(Money(cogs, currency)),
            }
        )

    return turnover_results
