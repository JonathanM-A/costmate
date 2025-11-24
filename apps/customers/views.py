from djmoney.money import Money
from django.db.models import Sum, Count, Q
from rest_framework.response import Response
from rest_framework import status
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from .serializers import (
    Customer,
    CustomerSerializer,
)
from ..users.utils import get_user_preferrence_from_cache
import logging

logger = logging.getLogger(__name__)


class CustomerViewset(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerSerializer
    queryset = Customer.objects.none()
    http_method_names = [m for m in ModelViewSet.http_method_names if m != "put"]
    search_fields = ["name", "contact", "email"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if not user.is_authenticated:
            return Customer.objects.none()

        base_queryset = (
            Customer.objects.all()
            if user.is_superuser
            else Customer.objects.filter(created_by=user, is_active=True)
        )

        return (
            base_queryset.select_related("created_by")
            .prefetch_related("orders")
            .order_by("-created_at")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def list(self, request, *args, **kwargs):
        result = super().list(request, *args, **kwargs)

        # Review before going live
        customer_stats = self.get_queryset().aggregate(
            total_customers=Count("id"),
            total_active=Count("id", filter=Q(is_active=True)),
            total_inactive=Count("id", filter=Q(is_active=False)),
        )
        result.data = {
            "customers": result.data,
            "stats": customer_stats,
        }
        return Response(result.data, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        try:
            result = super().retrieve(request, *args, **kwargs)

            customer = self.get_object()
            currency = get_user_preferrence_from_cache(request.user.id, "currency", "USD")

            total_orders = customer.orders.filter(is_active=True).count()
            total_spent = customer.orders.filter(is_active=True).aggregate(
                        total=Sum("total_value")
                    )["total"]
            
            avg_order_value = str(Money(total_spent / total_orders if total_orders > 0 else 0, currency))
            
            total_spent = str(
                Money(
                    total_spent if total_spent is not None else 0,
                    currency,
                )
            )

            stats = {
                "total_orders": total_orders,
                "total_spent": total_spent,
                "avg_order_value": avg_order_value,
            }
            result.data["stats"] = stats

            return Response(result.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error retrieving customer: {str(e)}")
            return Response(
                {"error": "An error occurred while retrieving the customer."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def destroy(self, request, *args, **kwargs):
        """Soft delete the customer by setting is_active to False."""
        instance = self.get_object()
        instance.deactivate()
        return Response(
            {"message": "Customer deleted successfully."},
            status=status.HTTP_204_NO_CONTENT,
        )
