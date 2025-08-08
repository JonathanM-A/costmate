from django.db import transaction
from django.db.models import Prefetch
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from .serializers import OrderSerializer, Order, OrderRecipe


class OrderViewSet(ModelViewSet):
    queryset = Order.objects.none()
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch"]
    search_fields = ["customer__name", "order_no"]
    filter_fields = ["status", "delivery_date"]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Order.objects.none()
        
        base_queryset = Order.objects.all() if user.is_superuser else Order.objects.filter(created_by=user)
        
        return base_queryset.select_related(
            "customer"
        ).prefetch_related(
            Prefetch(
                "order_recipes",
                queryset=OrderRecipe.objects.select_related("recipe"),
                to_attr="prefetched_order_recipes"
            )
        ).order_by("-created_at")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


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

        if new_status == "completed":
            with transaction.atomic():
                order_recipes = order.order_recipes.all()
                for order_recipe in order_recipes:
                    order_recipe.update_inventory(user)

        order.status = new_status
        order.save()

        serializer = self.get_serializer(order)
        return Response(serializer.data, status=200)
