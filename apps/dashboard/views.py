from datetime import datetime
from djmoney.money import Money
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import F, Sum, Count, DecimalField, Aggregate, TextField
from django.db.models.functions import Coalesce
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from ..orders.models import Order, OrderRecipe
from ..orders.serializers import OrderSerializer
from ..inventory.models import Inventory
from ..users.utils import get_user_preferrence_from_cache


class MoneyAggregate(Aggregate):
    function = "SUM"
    template = "%(function)s(%(expressions)s)"

    def __init__(self, expression, currency, **extra):
        super().__init__(expression, outputfield=TextField(), **extra)
        self.currency = currency

    def convert_value(self, value, expression, connection):
        if value is None:
            return str(Money(0, self.currency))
        return str(Money(value, self.currency))


class DashboardView(APIView):
    """Dashboard view to provide order statistics and low stock items.
    Optional filtering by date range using start_date and end_date query parameters.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Fetch fields filterable by date
        # Get start_date and end_date from kwargs (if provided)
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        # Default to current month if no dates provided
        if not start_date_str and not end_date_str:
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
        else:
            # Parse provided dates
            try:
                start_date = (
                    datetime.strptime(start_date_str, "%Y-%m-%d").date()
                    if start_date_str
                    else None
                )
            except ValueError:
                raise ValidationError(
                    "Invalid start_date format. Required format is YYYY-MM-DD."
                )
            try:
                end_date = (
                    datetime.strptime(end_date_str, "%Y-%m-%d").date()
                    if end_date_str
                    else None
                )
            except ValueError:
                raise ValidationError(
                    "Invalid end_date format. Required format is YYYY-MM-DD."
                )

        currency = get_user_preferrence_from_cache(request.user, "currency", "USD")

        completed_orders = Order.objects.filter(
            created_by=self.request.user, status="completed"
        ).prefetch_related("order_recipes")

        order_stats = completed_orders.aggregate(
            total_completed=Count("id"),
            total_cost=MoneyAggregate("total_value", currency=currency),
            total_profit=MoneyAggregate("profit", currency=currency),
            total_profit_percent=Sum("profit") / Count("id"),
        )

        if start_date:
            print(start_date)
            completed_orders = completed_orders.filter(
                created_at__gte=start_date, status="completed"
            )
        if end_date:
            completed_orders = completed_orders.filter(
                created_at__lte=end_date, status="completed"
            )

        chart_data = completed_orders.values_list(
            "created_at", "total_value", "profit"
        )  # List of (created_at, total_value, profit) tuples

        # fetch non-filterable fields

        recipe_stats = OrderRecipe.objects.filter(order__in=completed_orders).aggregate(
            ingredient_cost=MoneyAggregate(
                "recipe__inventory_items_cost", currency=currency
            ),
            overhead_cost=MoneyAggregate("recipe__overhead_cost", currency=currency),
            labour_cost=MoneyAggregate("recipe__labour_cost", currency=currency),
            packaging_cost=MoneyAggregate("recipe__packaging_cost", currency=currency),
        )

        # Combine results
        results = {**order_stats, **recipe_stats}

        pending_orders = Order.objects.filter(
            created_by=self.request.user, status="pending"
        )
        upcoming_orders = OrderSerializer(
            pending_orders.order_by("delivery_date")[:5],
            many=True,
            context={"request": request},
        ).data

        results["low_stock"] = Inventory.objects.filter(
            quantity__lt=F("reorder_level")
        ).count()
        results["active_orders"] = pending_orders.count()

        return Response(
            {
                "aggregates": results,
                "chart_data": list(chart_data),
                "upcoming_orders": upcoming_orders,
            },
            status=status.HTTP_200_OK,
        )
