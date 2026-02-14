import csv
import io
from datetime import datetime, timedelta
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.utils import timezone
from django.http import HttpResponse
from django.db.models import (
    Count,
    Sum,
    Avg,
    F,
    Case,
    When,
    ExpressionWrapper,
    DecimalField,
    Value,
)
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .utils import calculate_inventory_turnover
from ..dashboard.views import MoneyAggregate
from ..orders.models import Order
from ..users.utils import get_user_preferrence_from_cache
import logging

logger = logging.getLogger(__name__)


# Total amount ordered, total profits, total order count, total customers
class AnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get analytics data",
        operation_description="Get analytics data for a given date range",
        responses={
            200: openapi.Response(description="Analytics data"),
            400: openapi.Response(
                description="Invalid start_date format. Required format is YYYY-MM-DD"
            ),
            400: openapi.Response(
                description="Invalid end_date format. Required format is YYYY-MM-DD"
            ),
        },
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
    )

    def get(self, request, *args, **kwargs):
        user = request.user
        currency = get_user_preferrence_from_cache(user.id, "currency", "USD")

        # Fetch fields filterable by date
        # Get start_date and end_date from kwargs (if provided)
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        # Default to current month if no dates provided
        if not start_date_str and not end_date_str:
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today

        elif not start_date_str:
            # Only end_date provided
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            except ValueError:
                raise ValidationError(
                    "Invalid end_date format. Required format is YYYY-MM-DD."
                )
            # Set start_date to the first day of the month of end_date
            start_date = end_date.replace(day=1)
        elif not end_date_str:
            # Only start_date provided
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            except ValueError:
                raise ValidationError(
                    "Invalid start_date format. Required format is YYYY-MM-DD."
                )
            # Set end_date to the last day of the month of start_date
            if start_date.month == 12:
                end_date = start_date.replace(year=start_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = start_date.replace(month=start_date.month + 1, day=1) - timedelta(days=1)

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
            created_by=user,
            status="completed",
            created_at__gte=start_date,
            created_at__lte=end_date,
        ).prefetch_related("order_products")

        # Use preferred_final_price if set, otherwise use suggested_price
        effective_price = Case(
            When(preferred_final_price__isnull=False, then=F("preferred_final_price")),
            default=F("suggested_price"),
        )
        profit_expr = effective_price - F("total_cost")

        if completed_orders.exists():
            order_stats = completed_orders.aggregate(
                total_orders=Count("id"),
                total_amount_ordered=MoneyAggregate(effective_price, currency=currency),
                total_profit=MoneyAggregate(profit_expr, currency=currency),
                total_customers=Count("customer", distinct=True),
            )

            # List of (created_at, profit) tuples
            profit_stats = completed_orders.annotate(
                calculated_profit=profit_expr,
            ).values_list("created_at", "calculated_profit")

            total_order_revenue = (
                completed_orders.aggregate(total_revenue=Sum(effective_price))[
                    "total_revenue"
                ]
                or 0
            )

            # Calculate line revenue as: line_cost * (1 + profit_margin / 100)
            line_revenue_expr = F("order_products__line_cost") * (
                Value(1) + F("profit_margin") / Value(100)
            )

            revenue_by_product_category = (
                completed_orders.annotate(
                    category_name=F("order_products__product__category__name")
                )
                .values("category_name")
                .annotate(
                    # numeric sum used for calculation and ordering
                    total_revenue_amount=Sum(line_revenue_expr),
                    # formatted money representation for UI
                    total_revenue=MoneyAggregate(
                        line_revenue_expr,
                        currency=currency,
                    ),
                    # percentage of total_order_revenue; guard against divide-by-zero
                    revenue_percentage=Case(
                        When(
                            total_revenue_amount__gt=0,
                            then=ExpressionWrapper(
                                (F("total_revenue_amount") * Value(100.0))
                                / Value(total_order_revenue),
                                output_field=DecimalField(decimal_places=2),
                            ),
                        ),
                        default=Value(0.0),
                        output_field=DecimalField(decimal_places=2),
                    ),
                )
                .order_by("-total_revenue_amount")
            )

            product_stats = (
                completed_orders.values("order_products__product__name")
                .annotate(
                    total_quantity_sold=Sum("order_products__quantity"),
                    total_revenue=MoneyAggregate(line_revenue_expr, currency=currency),
                    profit_margin=Avg("profit_margin"),
                )
                .order_by("-total_quantity_sold")[:5]
            )
        else:
            order_stats = {
                "total_completed": 0,
                "total_revenue": 0,
                "total_profit": 0,
                "total_customers": 0,
            }
            profit_stats = []
            revenue_by_product_category = []
            product_stats = []

        # Inventory turnover calculation
        inventory_stats = calculate_inventory_turnover(
            user, start_date, end_date, currency
        )

        inventory_stats.sort(key=lambda x: x["turnover_ratio"], reverse=True)
        inventory_stats = inventory_stats[:5]

        return Response(
            {
                "order_stats": order_stats,
                "profit_stats": list(profit_stats),
                "revenue_by_product_category": list(revenue_by_product_category),
                "top_products": list(product_stats),
                "inventory_stats": inventory_stats,
            },
            status=status.HTTP_200_OK,
        )


class AnalyticsExportView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Export analytics data",
        operation_description="Export analytics data as CSV or Excel file",
        responses={
            200: openapi.Response(description="File download"),
            400: openapi.Response(description="Invalid format or date parameters"),
        },
        manual_parameters=[
            openapi.Parameter(
                "export_format",
                openapi.IN_QUERY,
                description="Export format: 'csv' or 'excel'",
                type=openapi.TYPE_STRING,
                required=True,
                enum=["csv", "excel"],
            ),
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
    )
    def get(self, request, *args, **kwargs):
        try:
            export_format = request.query_params.get("export_format", "").lower()

            if export_format not in ("csv", "excel"):
                raise ValidationError("Invalid export_format. Use 'csv' or 'excel'.")
            user = request.user
            currency = get_user_preferrence_from_cache(user.id, "currency", "USD")

            start_date_str = request.query_params.get("start_date")
            end_date_str = request.query_params.get("end_date")

            if not start_date_str and not end_date_str:
                today = timezone.now().date()
                start_date = today.replace(day=1)
                end_date = today
            elif not start_date_str:
                try:
                    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                except ValueError:
                    raise ValidationError(
                        "Invalid end_date format. Required format is YYYY-MM-DD."
                    )
                start_date = end_date.replace(day=1)
            elif not end_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                except ValueError:
                    raise ValidationError(
                        "Invalid start_date format. Required format is YYYY-MM-DD."
                    )
                if start_date.month == 12:
                    end_date = start_date.replace(
                        year=start_date.year + 1, month=1, day=1
                    ) - timedelta(days=1)
                else:
                    end_date = start_date.replace(
                        month=start_date.month + 1, day=1
                    ) - timedelta(days=1)
            else:
                try:
                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                except ValueError:
                    raise ValidationError(
                        "Invalid start_date format. Required format is YYYY-MM-DD."
                    )
                try:
                    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                except ValueError:
                    raise ValidationError(
                        "Invalid end_date format. Required format is YYYY-MM-DD."
                    )

            completed_orders = Order.objects.filter(
                created_by=user,
                status="completed",
                created_at__gte=start_date,
                created_at__lte=end_date,
            ).prefetch_related("order_products")

            effective_price = Case(
                When(preferred_final_price__isnull=False, then=F("preferred_final_price")),
                default=F("suggested_price"),
            )
            profit_expr = effective_price - F("total_cost")
            line_revenue_expr = F("order_products__line_cost") * (
                Value(1) + F("profit_margin") / Value(100)
            )

            if completed_orders.exists():
                order_stats = completed_orders.aggregate(
                    total_orders=Count("id"),
                    total_amount_ordered=Sum(effective_price),
                    total_profit=Sum(profit_expr),
                    total_customers=Count("customer", distinct=True),
                )

                revenue_by_product_category = list(
                    completed_orders.annotate(
                        category_name=F("order_products__product__category__name")
                    )
                    .values("category_name")
                    .annotate(total_revenue=Sum(line_revenue_expr))
                    .order_by("-total_revenue")
                )

                top_products = list(
                    completed_orders.values("order_products__product__name")
                    .annotate(
                        total_quantity_sold=Sum("order_products__quantity"),
                        total_revenue=Sum(line_revenue_expr),
                        profit_margin=Avg("profit_margin"),
                    )
                    .order_by("-total_quantity_sold")[:5]
                )
            else:
                order_stats = {
                    "total_orders": 0,
                    "total_amount_ordered": 0,
                    "total_profit": 0,
                    "total_customers": 0,
                }
                revenue_by_product_category = []
                top_products = []

            inventory_stats = calculate_inventory_turnover(
                user, start_date, end_date, currency
            )
            inventory_stats.sort(key=lambda x: x["turnover_ratio"], reverse=True)
            inventory_stats = inventory_stats[:5]

            filename = f"analytics_{start_date}_{end_date}"

            logger.info(f"Exporting analytics data for user {user.id} from {start_date} to {end_date} as {export_format.upper()}")

            if export_format == "csv":
                return self._export_csv(
                    filename,
                    order_stats,
                    revenue_by_product_category,
                    top_products,
                    inventory_stats,
                )
            else:
                return self._export_excel(
                    filename,
                    order_stats,
                    revenue_by_product_category,
                    top_products,
                    inventory_stats,
                )
        except Exception as e:
            logger.error(f"Error exporting analytics data: {str(e)}")
            raise ValidationError(f"Error exporting analytics data: {str(e)}")

    def _export_csv(
        self,
        filename,
        order_stats,
        revenue_by_category,
        top_products,
        inventory_stats,
    ):
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["ANALYTICS REPORT"])
        writer.writerow([])

        writer.writerow(["ORDER SUMMARY"])
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Total Orders", order_stats["total_orders"]])
        writer.writerow(["Total Amount Ordered", order_stats["total_amount_ordered"]])
        writer.writerow(["Total Profit", order_stats["total_profit"]])
        writer.writerow(["Total Customers", order_stats["total_customers"]])
        writer.writerow([])

        writer.writerow(["REVENUE BY CATEGORY"])
        writer.writerow(["Category", "Revenue"])
        for item in revenue_by_category:
            writer.writerow([item["category_name"] or "Uncategorized", item["total_revenue"]])
        writer.writerow([])

        writer.writerow(["TOP PRODUCTS"])
        writer.writerow(["Product", "Quantity Sold", "Revenue", "Profit Margin %"])
        for item in top_products:
            writer.writerow([
                item["order_products__product__name"],
                item["total_quantity_sold"],
                item["total_revenue"],
                round(item["profit_margin"], 2) if item["profit_margin"] else 0,
            ])
        writer.writerow([])

        writer.writerow(["INVENTORY TURNOVER (Top 5)"])
        writer.writerow(["Item", "Turnover Ratio", "Cost"])
        for item in inventory_stats:
            writer.writerow([item["item_name"], item["turnover_ratio"], item["cost"]])

        output.seek(0)
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
        return response

    def _export_excel(
        self,
        filename,
        order_stats,
        revenue_by_category,
        top_products,
        inventory_stats,
    ):
        from openpyxl import Workbook
        from openpyxl.styles import Font

        wb = Workbook()
        ws = wb.active
        ws.title = "Analytics Report"

        bold_font = Font(bold=True)
        header_font = Font(bold=True, size=14)

        row = 1
        ws.cell(row=row, column=1, value="ANALYTICS REPORT").font = header_font
        row += 2

        ws.cell(row=row, column=1, value="ORDER SUMMARY").font = bold_font
        row += 1
        ws.cell(row=row, column=1, value="Metric").font = bold_font
        ws.cell(row=row, column=2, value="Value").font = bold_font
        row += 1
        ws.cell(row=row, column=1, value="Total Orders")
        ws.cell(row=row, column=2, value=order_stats["total_orders"])
        row += 1
        ws.cell(row=row, column=1, value="Total Amount Ordered")
        ws.cell(row=row, column=2, value=float(order_stats["total_amount_ordered"] or 0))
        row += 1
        ws.cell(row=row, column=1, value="Total Profit")
        ws.cell(row=row, column=2, value=float(order_stats["total_profit"] or 0))
        row += 1
        ws.cell(row=row, column=1, value="Total Customers")
        ws.cell(row=row, column=2, value=order_stats["total_customers"])
        row += 2

        ws.cell(row=row, column=1, value="REVENUE BY CATEGORY").font = bold_font
        row += 1
        ws.cell(row=row, column=1, value="Category").font = bold_font
        ws.cell(row=row, column=2, value="Revenue").font = bold_font
        row += 1
        for item in revenue_by_category:
            ws.cell(row=row, column=1, value=item.get("category_name") or "Uncategorized")
            revenue_val = item.get("total_revenue") or 0
            ws.cell(row=row, column=2, value=float(revenue_val) if revenue_val else 0)
            row += 1
        row += 1

        ws.cell(row=row, column=1, value="TOP PRODUCTS").font = bold_font
        row += 1
        ws.cell(row=row, column=1, value="Product").font = bold_font
        ws.cell(row=row, column=2, value="Quantity Sold").font = bold_font
        ws.cell(row=row, column=3, value="Revenue").font = bold_font
        ws.cell(row=row, column=4, value="Profit Margin %").font = bold_font
        row += 1
        for item in top_products:
            ws.cell(row=row, column=1, value=item.get("order_products__product__name") or "Unknown")
            qty = item.get("total_quantity_sold") or 0
            revenue = item.get("total_revenue") or 0
            margin = item.get("profit_margin") or 0
            ws.cell(row=row, column=2, value=float(qty) if qty else 0)
            ws.cell(row=row, column=3, value=float(revenue) if revenue else 0)
            ws.cell(row=row, column=4, value=round(float(margin), 2) if margin else 0)
            row += 1
        row += 1

        ws.cell(row=row, column=1, value="INVENTORY TURNOVER (Top 5)").font = bold_font
        row += 1
        ws.cell(row=row, column=1, value="Item").font = bold_font
        ws.cell(row=row, column=2, value="Turnover Ratio").font = bold_font
        ws.cell(row=row, column=3, value="Cost").font = bold_font
        row += 1
        for item in inventory_stats:
            ws.cell(row=row, column=1, value=item.get("item_name") or "Unknown")
            ws.cell(row=row, column=2, value=item.get("turnover_ratio") or 0)
            ws.cell(row=row, column=3, value=str(item.get("cost") or "0"))
            row += 1

        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[column].width = max_length + 2

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
        return response
