from datetime import datetime
from djmoney.money import Money
from decimal import Decimal
from django.db.models import (
    Q,
    F,
    BooleanField,
    Case,
    When,
    Value,
    Sum,
    Count,
    IntegerField,
    Prefetch,
)
from django.db import transaction
from rest_framework.response import Response
from rest_framework import status
from rest_framework.viewsets import ModelViewSet
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from djmoney.money import Money
from .models import InventoryItem, Supplier, Inventory, InventoryHistory, InventoryUnit
from .serializers import (
    InventoryItemSerializer,
    SupplierSerializer,
    InventorySerializer,
    InventoryHistorySerializer,
    InventoryUnitSerializer
)
from .filters import InventoryFilter
from ..recipes.serializers import RecipeSerializer
from ..users.permissions import IsSubscriptionActive
from ..users.utils import get_user_preferrence_from_cache
import logging

logger = logging.Logger(__name__)


class InventoryUnitView(ModelViewSet):
    queryset = InventoryUnit.objects.none()
    serializer_class = InventoryUnitSerializer
    permission_classes = [IsSubscriptionActive]
    http_method_names = ["get", "post"]
    search_fields = ["name", "unit_symbol"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if not user.is_authenticated:
            return InventoryUnit.objects.none()

        base_queryset = (
            InventoryUnit.objects.all()
            if user.is_superuser
            else InventoryUnit.objects.filter(
                Q(created_by=user) | Q(is_default=True), is_active=True
            )
        )
        return base_queryset.select_related("created_by").order_by("name")


class InventoryItemView(ModelViewSet):
    """
    - **GET /inventory-items**: List/filter inventory items
    """
    queryset = InventoryItem.objects.none()
    serializer_class = InventoryItemSerializer
    permission_classes = [IsSubscriptionActive]
    http_method_names = ["get", "post", "patch"]
    search_fields = ["name"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if not user.is_authenticated:
            return InventoryItem.objects.none()

        base_queryset = (
            InventoryItem.objects.all()
            if user.is_superuser
            else InventoryItem.objects.filter(
                Q(created_by=user) | Q(is_default=True), is_active=True
            )
        )
        return base_queryset.select_related("created_by").prefetch_related("inventory").order_by("name")
    
    def update(self, request, *args, **kwargs):
        object_instance = self.get_object()
        if object_instance.is_default:
            raise ValidationError(
                {"error": "Default inventory items cannot be modified."}
            )
        return super().update(request, *args, **kwargs)


class SupplierViewset(ModelViewSet):
    queryset = Supplier.objects.none()
    serializer_class = SupplierSerializer
    permission_classes = [IsSubscriptionActive]
    search_fields = ["name", "contact"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if not user.is_authenticated:
            return Supplier.objects.none()

        base_queryset = (
            Supplier.objects.all()
            if user.is_superuser
            else Supplier.objects.filter(is_active=True, created_by=user)
        )
        return (
            base_queryset.select_related("created_by")
            .prefetch_related("history")
            .order_by("name")
        )

    def list(self, request, *args, **kwargs):
        result = super().list(request, *args, **kwargs)

        currency = get_user_preferrence_from_cache(request.user.id, "currency", "USD")

        supplier_stats = self.get_queryset().aggregate(
            total_suppliers=Count("id"),
            total_spent=Sum("history__cost_price"),
        )

        supplier_stats["total_spent"] = str(
            Money(supplier_stats["total_spent"], currency) if supplier_stats["total_spent"] else Money(0, currency)
        )

        result.data = {
            "suppliers": result.data,
            "stats": supplier_stats,
        }

        return Response(result.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.deactivate()
        return Response(
            {"message": "Supplier deleted successfully."},
            status=status.HTTP_204_NO_CONTENT,
        )

    @action(methods=["get"], detail=False, url_path="price-tracking")
    def inventory_price_tracking(self, request, *args, **kwargs):
        """Retrieve inventory history and compare cost price changes between two most recent entries of the last 5 inventory added."""

        user = request.user
        inventory_items = InventoryItem.objects.filter(
            Q(created_by=user) | Q(is_default=True), is_active=True
        ).prefetch_related(
            Prefetch(
                "history",
                queryset=InventoryHistory.objects.filter(
                    is_addition=True, created_by=user
                ).order_by("-incident_date", "-created_at"),
            )
        )

        result = []
        count = 0
        for item in inventory_items:
            history = item.history.all()[:2]  # type: ignore
            if len(history) >= 2:
                count += 1
                if count > 5:
                    break
                latest = history[0]
                previous = history[1]
                price_change = latest.cost_per_unit - previous.cost_per_unit
                price_change_percentage = (
                    (price_change / previous.cost_per_unit) * 100
                    if previous.cost_per_unit != 0
                    else 0
                )
                result.append(
                    {
                        "ingredient": item.name,
                        "current_price": str(
                            Money(
                                latest.cost_per_unit,
                                get_user_preferrence_from_cache(
                                    user.id, "currency", "USD"
                                ),
                            )
                        ),
                        "previous_price": str(
                            Money(
                                previous.cost_per_unit,
                                get_user_preferrence_from_cache(
                                    user.id, "currency", "USD"
                                ),
                            )
                        ),
                        "price_change_percentage": f"{round(price_change_percentage, 2)}%",
                        "last_updated": latest.incident_date,
                        "supplier": latest.supplier.name if latest.supplier else "N/A",
                    }
                )
        return Response({"results":result}, status=status.HTTP_200_OK)


class InventoryView(ModelViewSet):
    queryset = Inventory.objects.none()
    serializer_class = InventorySerializer
    permission_classes = [IsSubscriptionActive]
    http_method_names = ["get", "delete", "post", "patch", "put"]
    search_fields = ["inventory_item__name"]
    filterset_class = InventoryFilter

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if not user.is_authenticated:
            return Inventory.objects.none()

        base_queryset = (
            Inventory.objects.all()
            if user.is_superuser
            else Inventory.objects.filter(created_by=user, is_active=True)
        )

        inventory_prefetch = Prefetch(
            "inventory_item__inventory",
            queryset=Inventory.objects.filter(created_by=user, is_active=True),
            to_attr="user_inventory",
        )

        return base_queryset.annotate(
            below_reorder=Case(
                When(quantity__lt=F("reorder_level"), then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        ).prefetch_related(inventory_prefetch).select_related("inventory_item").order_by("inventory_item__name")

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            instances = serializer.save()
            return Response(
                InventoryHistorySerializer(
                    instances, many=True, context={"request": request}
                ).data,
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.error(f"Error creating inventory: {e}")
            return Response(
                {"error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )

    def list(self, request, *args, **kwargs):
        base_queryset = self.get_queryset()
        user = self.request.user

        if base_queryset:
            # Add aggregated data to the response
            aggregated_data = base_queryset.aggregate(
                low_stock_level=Count(
                    Case(
                        When(quantity__lt=F("reorder_level"), then=1),
                        output_field=IntegerField(),
                    )
                ),
                good_stock_level=Count(
                    Case(
                        When(quantity__gte=F("reorder_level"), then=1),
                        output_field=IntegerField(),
                    )
                ),
                total_value=Sum("total_value"),
                total_inventory=Count("id")
            )

            queryset = self.filter_queryset(self.get_queryset())

            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)

                response = self.get_paginated_response(serializer.data)
                response.data.update(aggregated_data)
                response.data["total_value"] = str(
                    Money(
                        aggregated_data["total_value"],
                        get_user_preferrence_from_cache(
                            user.id, "currency", "USD"
                        ),
                    )
                )
                return response

            serializer = self.get_serializer(queryset, many=True)
            response_data = {
                "results": serializer.data,
                **aggregated_data,
                "total_value": str(
                    Money(
                        aggregated_data["total_value"] or 0,
                        get_user_preferrence_from_cache(
                            user.id, "currency", "USD"
                        ),
                    )
                ),
            }
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            return Response(
                {
                    "results": [],
                    "low_stock_level": 0,
                    "good_stock_level": 0,
                    "total_value": str(
                        Money(
                            0,
                            get_user_preferrence_from_cache(
                                user.id, "currency", "USD" # type: ignore
                            ),
                        )
                    ),
                    "total_inventory": 0,
                },
                status=status.HTTP_200_OK,
            )

    def partial_update(self, request, *args, **kwargs):
        allowed_fields = {"reorder_level"}
        incoming_fields = set(request.data.keys())

        if not incoming_fields.issubset(allowed_fields):
            raise ValidationError(
                f"You can only update the following field(s): {allowed_fields}"
            )
        instance = self.get_object()
        new_reorder_level = self.request.data.get("reorder_level")
        if new_reorder_level:
            instance.reorder_level = new_reorder_level
            instance.save()

            return Response(
                {"message": "Reorder level updated."}, status=status.HTTP_200_OK
            )
        raise ValidationError({"error": "Reorder level not provided"})

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        quantity = instance.quantity

        with transaction.atomic():
            inventory_history_data = {
                "inventory_item_id": instance.inventory_item.id,
                "quantity": quantity,
                "is_addition": False,
                "incident_date": None,
            }

            serializer = InventoryHistorySerializer(
                data=inventory_history_data, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

            instance.delete()

        return Response(
            {"message": "Inventory entry deleted successfully."},
            status=status.HTTP_204_NO_CONTENT,
        )

    @action(methods=["put"], detail=True, url_path="decrease")
    def decrease_stock(self, request, *args, pk=None, **kwargs):
        inventory = self.get_object()
        quantity = Decimal(request.data.get("quantity", 0))
        incident_date = request.data.get("incident_date", datetime.today())
        
        if isinstance(incident_date, str):
            try:
                incident_date = datetime.strptime(incident_date, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"error": "Invalid incident_date format. Required format is YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if quantity <= 0:
            return Response(
                {"error": "Quantity must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if incident_date > datetime.today().date():
            return Response(
                {"error": "Incident date cannot be in the future."},
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
            inventory.calculate_total_value()

            # Log the inventory history
            inventory_history_data = {
                "inventory_item_id": inventory.inventory_item.id,
                "quantity": quantity,
                "is_addition": False,
                "incident_date": incident_date,
            }
            serializer = InventoryHistorySerializer(
                data=inventory_history_data, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

        return Response(
            {"message": "Stock decreased successfully."}, status=status.HTTP_200_OK
        )

    @action(methods=["get"], detail=True, url_path="history")
    def view_inventory_item_history(self, request, *args, **kwargs):
        inventory = self.get_object()
        history = (
            InventoryHistory.objects.filter(
                inventory_item=inventory.inventory_item, created_by=request.user
            )
            .order_by("-created_at")
            .select_related("supplier")
        )
        serializer = InventoryHistorySerializer(
            history, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(methods=["get"], detail=True, url_path="recipes")
    def view_inventory_item_recipes(self, request, *args, **kwargs):
        inventory = self.get_object()
        recipes = inventory.inventory_item.recipes.filter(
            created_by=request.user
        ).prefetch_related("ingredients__inventory_item")
        serializer = RecipeSerializer(recipes, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class InventoryHistoryView(ListAPIView):
    queryset = InventoryHistory.objects.none()
    serializer_class = InventoryHistorySerializer
    permission_classes = [IsSubscriptionActive]
    filterset_fields = [
        "created_at",
        "incident_date",
        "inventory_item__name",
        "supplier__name",
        "is_addition",
    ]
    search_fields = ["inventory_item__name", "supplier__name"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if user.is_authenticated:
            if user.is_superuser:
                return (
                    InventoryHistory.objects.all()
                    .select_related("inventory_item", "supplier")
                    .order_by("-incident_date", "-created_at")
                )
            else:
                return (
                    InventoryHistory.objects.filter(created_by=user)
                    .select_related("inventory_item", "supplier")
                    .order_by("-incident_date", "-created_at")
                )
