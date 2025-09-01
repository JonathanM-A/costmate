from datetime import datetime
from django.utils import timezone
from django.db.models import Count, Sum, Avg
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .utils import calculate_inventory_turnover
from ..dashboard.views import MoneyAggregate
from ..orders.models import Order
from ..users.utils import get_user_preferrence_from_cache


# Total amount ordered, total profits, total order count, total customers
class AnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        currency = get_user_preferrence_from_cache(user, "currency", "USD")

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

        completed_orders = Order.objects.filter(
                created_by=user, status="completed", created_at__gte=start_date, created_at__lte=end_date
            ).prefetch_related("order_recipes")

        
        if completed_orders.exists():
            order_stats = completed_orders.aggregate(
                total_completed=Count("id"),
                total_revenue=MoneyAggregate("total_value", currency=currency),
                total_profit=MoneyAggregate("profit", currency=currency),
                total_customers=Count("customer", distinct=True),
            )

            # List of (created_at, profit) tuples
            profit_stats = completed_orders.values_list("created_at", "profit")

            revenue_by_recipe_category = completed_orders.values(
                "order_recipes__recipe__category__name"
            ).annotate(total_revenue=MoneyAggregate("total_value", currency=currency)).order_by(
                "-total_revenue"
            )

            recipe_stats = (
                completed_orders.values(
                    "order_recipes__recipe__name"
                )
                .annotate(
                    total_quantity_sold=Sum("order_recipes__quantity"),
                    total_revenue=MoneyAggregate("total_value", currency=currency),
                    profit_margin=Avg("order_recipes__recipe__profit_margin"),
                )
                .order_by("-total_revenue")[:5]
            )
        else:
            order_stats = {
                "total_completed": 0,
                "total_revenue": 0,
                "total_profit": 0,
                "total_customers": 0,
            }
            profit_stats = []
            revenue_by_recipe_category = []
            recipe_stats = []
        
        # Inventory turnover calculation
        inventory_stats = calculate_inventory_turnover(user, start_date, end_date, currency)
        
        inventory_stats.sort(key=lambda x: x["turnover_ratio"], reverse=True)
        inventory_stats = inventory_stats[:5]

        return Response(
            {
                "order_stats": order_stats,
                "profit_stats": list(profit_stats),
                "revenue_by_recipe_category": list(revenue_by_recipe_category),
                "top_recipes": list(recipe_stats),
                "inventory_stats": inventory_stats,
            },
            status=status.HTTP_200_OK,
        )
