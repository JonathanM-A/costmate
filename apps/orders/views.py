from datetime import date
from djmoney.money import Money
from django.db.models import Prefetch, Count, Sum, Q
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import status
from .serializers import (
    OrderSerializer,
    Order,
    OrderRecipe,
    Overhead,
    OverheadSerializer,
    BulkOverheadUpdateSerializer,
)
from ..users.permissions import IsSubscriptionActive
from ..users.utils import get_user_preferrence_from_cache, update_onboarding_metric


class OrderViewSet(ModelViewSet):
    queryset = Order.objects.none()
    serializer_class = OrderSerializer
    permission_classes = [IsSubscriptionActive]
    http_method_names = ["get", "post", "patch"]
    search_fields = ["customer__name", "order_no"]
    filterset_fields = [
        "status",
        "delivery_date",
        "created_at",
        "customer__id",
        "order_recipes__recipe__category__name",
    ]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if not user.is_authenticated:
            return Order.objects.none()

        base_queryset = (
            Order.objects.all()
            if user.is_superuser
            else Order.objects.filter(created_by=user, is_active=True)
        )

        return (
            base_queryset.select_related("customer")
            .prefetch_related(
                Prefetch(
                    "order_recipes",
                    queryset=OrderRecipe.objects.select_related("recipe"),
                    to_attr="prefetched_order_recipes",
                )
            )
            .order_by("delivery_date", "created_at")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED:
            update_onboarding_metric(request.user, "has_created_order")
        return response

    def retrieve(self, request, *args, **kwargs):
        results = super().retrieve(request, *args, **kwargs)

        tax_enabled = get_user_preferrence_from_cache(
            request.user.id, "tax_enabled", False
        )

        results.data = {
            "order": results.data,
            "tax_enabled": tax_enabled,
        }
        return Response(results.data, status=status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):
        result = super().list(request, *args, **kwargs)

        tax_enabled = get_user_preferrence_from_cache(
            request.user.id, "tax_enabled", False
        )

        order_stats = self.get_queryset().aggregate(
            total_orders=Count("id", filter=Q(status__in=["completed", "pending"])),
            total_pending=Count("id", filter=Q(status="pending")),
            due_today=Count(
                "id",
                filter=Q(
                    status="pending",
                    delivery_date=date.today(),
                ),
            ),
            total_revenue=Sum("final_price", filter=Q(status="completed")),
            total_cost=Sum("total_cost", filter=Q(status="completed")),
        )

        currency = get_user_preferrence_from_cache(request.user.id, "currency", "USD")

        total_revenue = order_stats["total_revenue"] or 0
        total_cost = order_stats["total_cost"] or 0
        total_profit = total_revenue - total_cost

        order_stats["total_revenue"] = str(Money(total_revenue, currency))
        order_stats["total_cost"] = str(Money(total_cost, currency))
        order_stats["total_profit"] = str(Money(total_profit, currency))

        result.data = {
            "orders": result.data,
            "stats": {**order_stats},
            "tax_enabled": tax_enabled,
        }
        return Response(result.data, status=status.HTTP_200_OK)

    @action(methods=["patch"], detail=True, url_path="update-status")
    def update_status(self, request, pk=None, **kwargs):
        order = self.get_object()
        user = self.request.user
        new_status = request.data.get("status")

        if new_status not in ["pending", "completed", "cancelled"]:
            return Response({"detail": "Invalid status."}, status=400)
        if order.status == new_status:
            return Response(
                {"detail": "Order status is already set to this value."}, status=400
            )

        if new_status == "completed":
            if order.status == "cancelled":
                return Response(
                    {"detail": "Cannot complete a cancelled order."}, status=400
                )

            # Check inventory availability before completing order
            is_available, insufficient_items = order.check_inventory_availability()
            if not is_available:
                error_message = "Cannot complete order. Insufficient inventory:"
                return Response(
                    {"detail": error_message, "insufficient_items": insufficient_items},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Update inventory for each order recipe
            for order_recipe in order.order_recipes.all():
                order_recipe.update_inventory(user)

        elif new_status == "cancelled":
            if order.status == "completed":
                return Response(
                    {"detail": "Cannot cancel a completed order."}, status=400
                )
        elif new_status == "pending":
            if order.status == "completed":
                return Response(
                    {"detail": "Cannot revert a completed order to pending."},
                    status=400,
                )
            elif new_status == "cancelled":
                return Response(
                    {"detail": "Cannot revert a cancelled order to pending."},
                    status=400,
                )

        order.status = new_status
        order.save()

        serializer = self.get_serializer(order)
        return Response(serializer.data, status=200)


class OverheadViewSet(ModelViewSet):
    queryset = Overhead.objects.none()
    serializer_class = OverheadSerializer
    permission_classes = [IsSubscriptionActive]
    http_method_names = ["get", "post", "put", "delete"]
    search_fields = ["name"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if not user.is_authenticated:
            return Overhead.objects.none()

        return (
            Overhead.objects.all()
            if user.is_superuser
            else Overhead.objects.filter(created_by=user)
        ).order_by("name")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED:
            update_onboarding_metric(request.user, "has_calculated_overhead")
        return response

    def list(self, request, *args, **kwargs):
        result = super().list(request, *args, **kwargs)

        estimated_monthly_orders = get_user_preferrence_from_cache(
            request.user.id, "estimated_monthly_orders", 10
        )
        currency = get_user_preferrence_from_cache(request.user.id, "currency", "USD")

        qs = self.get_queryset()
        total_monthly_value = qs.aggregate(total=Sum("monthly_cost"))["total"] or 0
        estimated_overhead_per_order = (
            (total_monthly_value / estimated_monthly_orders)
            if estimated_monthly_orders > 0
            else 0
        )

        result.data = {
            "overheads": result.data,
            "estimated_overhead_per_order": str(
                Money(
                    estimated_overhead_per_order,
                    currency,
                )
            ),
            "estimated_monthly_orders": estimated_monthly_orders,
            "total_yearly_overhead": str(Money(total_monthly_value * 12, currency)),
        }

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data = {"overheads": response.data, **stats}
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({"overheads": serializer.data, **stats}, status=status.HTTP_200_OK)
