from django.db.models import Q, F, BooleanField, Case, When, Value
from django.db import transaction
from rest_framework.response import Response
from rest_framework import status
from rest_framework.viewsets import ModelViewSet
from rest_framework.generics import ListCreateAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from .models import InventoryItem, Supplier, Inventory, InventoryHistory
from .serializers import (
    InventoryItemSerializer,
    SupplierSerializer,
    InventorySerializer,
    InventoryHistorySerializer,
)


class InventoryItemView(ListCreateAPIView):
    queryset = InventoryItem.objects.none()
    serializer_class = InventoryItemSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["name"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if user.is_authenticated:
            if user.is_superuser:
                return InventoryItem.objects.all()
            return InventoryItem.objects.filter(
                Q(created_by=user) | Q(is_default=True), is_active=True
            )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class SupplierViewset(ModelViewSet):
    queryset = Supplier.objects.none()
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["name", "contact"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if user.is_authenticated:
            if user.is_superuser:
                return Supplier.objects.all()
            return Supplier.objects.filter(created_by=user, is_active=True)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.deactivate()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InventoryView(ModelViewSet):
    queryset = Inventory.objects.none()
    serializer_class = InventorySerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "delete", "post", "put"]
    search_fields = ["item__name"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if user.is_authenticated:
            if user.is_superuser:
                return Inventory.objects.all()
            return Inventory.objects.filter(created_by=user, is_active=True).annotate(
                below_reorder=Case(
                    When(quantity__lt=F("reorder_level"), then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField(),
                )
            )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    @action(methods=["put"], detail=True, url_path="decrease-stock")
    def decrease_stock(self, request, pk=None):
        inventory = self.get_object()
        quantity = request.data.get("quantity", 0)
        if quantity <= 0:
            return Response(
                {"error": "Quantity must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if inventory.quantity < quantity:
            return Response(
                {"error": "Insufficient stock."}, status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # Decrease the stock
            updated = Inventory.objects.filter(pk=pk, quantity__gte=quantity).update(
                quantity=F("quantity") - quantity
            )
            if not updated:
                return Response(
                    {"error": "Failed to decrease stock."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            inventory.refresh_from_db()

            # Log the inventory history
            inventory_history_data={
                "inventory_item":inventory.inventory_item,
                "quantity":quantity,
                "is_addition":False,
                "purchase_date":None,
                "created_by":request.user,
            }
            serializer = InventoryHistorySerializer(data=inventory_history_data)
            serializer.is_valid(raise_exception=True)
            serializer.save()

        return Response(
            {"message": "Stock decreased successfully."}, status=status.HTTP_200_OK
        )


class InventoryHistoryView(ListAPIView):
    queryset = InventoryHistory.objects.none()
    serializer_class = InventoryHistorySerializer
    permission_classes = [IsAuthenticated]
    filter_fields = [
        "created_at",
        "purchase_date",
        "inventory_item",
        "supplier",
        "is_addition",
    ]
    search_fields = ["inventory_item__name", "supplier__name"]
