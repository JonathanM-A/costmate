from datetime import datetime
from djmoney.money import Money
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import F, Sum, Count, Aggregate, TextField, Case, When
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from ..orders.models import Order, OrderProduct
from ..orders.serializers import OrderSerializer
from ..inventory.models import Inventory
from ..users.utils import get_user_preferrence_from_cache


class MoneyAggregate(Aggregate):
    function = "SUM"
    template = "%(function)s(%(expressions)s)"

    def __init__(self, expression, currency, **extra):
        super().__init__(expression, outputfield=TextField(), **extra)
        self.currency = currency

    def convert_value(self, value, expression, connection): # type: ignore
        if value is None:
            return str(Money(0, self.currency))
        return str(Money(value, self.currency))


class DashboardView(APIView):
    """Dashboard view to provide order statistics and low stock items.
    Optional filtering by date range using start_date and end_date query parameters.
    """

    permission_classes=[IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get dashboard data",
        operation_description="Get dashboard data with optional date range filtering.",
        manual_parameters=[
            openapi.Parameter(
                "start_date",
                openapi.IN_QUERY,
                description="Start date in YYYY-MM-DD format",
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "end_date",
                openapi.IN_QUERY,
                description="End date in YYYY-MM-DD format",
                type=openapi.TYPE_STRING,
            ),
        ],
        responses={
            200: openapi.Response(description="Dashboard data"),
            400: openapi.Response(
                description="Invalid start_date format. Required format is YYYY-MM-DD."
            ),
            400: openapi.Response(
                description="Invalid end_date format. Required format is YYYY-MM-DD."
            ),
        },
    )

    def get(self, request, *args, **kwargs):
        user = self.request.user
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

        currency = get_user_preferrence_from_cache(user.id, "currency", "USD")

        completed_orders = Order.objects.filter(
            created_by=user, status="completed"
        ).prefetch_related("order_products")

        # Use preferred_final_price if set, otherwise use suggested_price
        effective_price = Case(
            When(preferred_final_price__isnull=False, then=F("preferred_final_price")),
            default=F("suggested_price"),
        )
        profit_expr = effective_price - F("total_cost")

        order_stats = completed_orders.aggregate(
            total_completed=Count("id"),
            agg_total_cost=MoneyAggregate(effective_price, currency=currency),
            total_profit=MoneyAggregate(profit_expr, currency=currency),
            total_profit_sum=Sum(profit_expr),
            total_revenue_sum=Sum(effective_price),
        )
        # Rename to preserve API response field name
        order_stats["total_cost"] = order_stats.pop("agg_total_cost")

        total_revenue = order_stats.pop("total_revenue_sum") or 0
        total_profit_raw = order_stats.pop("total_profit_sum") or 0
        order_stats["total_profit_percent"] = round((total_profit_raw / total_revenue * 100) if total_revenue else 0, 2)

        if start_date:
            completed_orders = completed_orders.filter(
                created_at__gte=start_date
            )
        if end_date:
            completed_orders = completed_orders.filter(
                created_at__lte=end_date
            )

        chart_data = completed_orders.annotate(
            effective_price=effective_price,
            profit=profit_expr,
        ).values_list(
            "created_at", "effective_price", "profit"
        )  # List of (created_at, effective_price, profit) tuples

        # fetch non-filterable fields

        # Get ingredient and labour costs from OrderProduct -> Product
        product_stats = OrderProduct.objects.filter(order__in=completed_orders).aggregate(
            ingredient_cost=MoneyAggregate(
                F("product__recipes_cost") * F("quantity"), currency=currency
            ),
            labour_cost=MoneyAggregate(
                F("product__labour_cost") * F("quantity"), currency=currency
            ),
        )
        # Get overhead and packaging costs from Order model
        order_cost_stats = completed_orders.aggregate(
            agg_overhead_cost=MoneyAggregate("overhead", currency=currency),
            agg_packaging_cost=MoneyAggregate("packaging", currency=currency),
        )
        product_stats["overhead_cost"] = order_cost_stats["agg_overhead_cost"]
        product_stats["packaging_cost"] = order_cost_stats["agg_packaging_cost"]

        # Combine results
        results = {**order_stats, **product_stats}

        pending_orders = Order.objects.filter(
            created_by=self.request.user, status="pending"
        )
        upcoming_orders = OrderSerializer(
            pending_orders.order_by("delivery_date")[:5],
            many=True,
            context={"request": request},
        ).data

        inventory_below_reorder = Inventory.objects.filter(
            quantity__lt=F("reorder_level"), created_by=request.user
        ).annotate(
            deficit_percentage=((F("reorder_level") - F("quantity")) * 100) / F("reorder_level")
        ).order_by(
            "-deficit_percentage"
        )

        inventory_alert = inventory_below_reorder.values_list("inventory_item__name", flat=True)
        results["inventory_alert"] = inventory_alert
        results["low_stock"] = inventory_below_reorder.count()
        results["active_orders"] = pending_orders.count()

        return Response(
            {
                "aggregates": results,
                "chart_data": list(chart_data),
                "upcoming_orders": upcoming_orders,
            },
            status=status.HTTP_200_OK,
        )
