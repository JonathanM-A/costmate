from datetime import date
from djmoney.money import Money
from django.db.models import Prefetch, Count, Sum, Q
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .serializers import OrderSerializer, Order, OrderRecipe
from ..users.permissions import IsSubscriptionActive
from ..users.utils import get_user_preferrence_from_cache


class OrderViewSet(ModelViewSet):
    queryset = Order.objects.none()
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsSubscriptionActive]
    http_method_names = ["get", "post", "patch"]
    search_fields = ["customer__name", "order_no"]
    filterset_fields = ["status", "delivery_date", "created_at", "customer__id", "order_recipes__recipe__category__name"]

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

    def list(self, request, *args, **kwargs):
        result = super().list(request, *args, **kwargs)

        order_stats = self.get_queryset().aggregate(
            total_orders=Count("id", filter=Q(status="completed")),
            total_pending=Count("id", filter=Q(status="pending")),
            due_today=Count(
                "id",
                filter=Q(
                    status="pending",
                    delivery_date=date.today(),
                ),
            ),
            total_amount=Sum("total_value", filter=Q(status="completed")),
            total_profit=Sum("profit", filter=Q(status="completed")),
        )

        currency = get_user_preferrence_from_cache(request.user.id, "currency", "USD")

        order_stats["total_amount"] = str(
            Money(order_stats["total_amount"] or 0, currency)
        )

        order_stats["total_profit"] = str(
            Money(order_stats["total_profit"] or 0, currency)
        )

        result.data = {
            "orders": result.data,
            "stats": {**order_stats},
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
