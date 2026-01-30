from djmoney.money import Money
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce
from rest_framework.response import Response
from rest_framework import status
from rest_framework.viewsets import ModelViewSet
from .serializers import (
    Customer,
    CustomerSerializer,
)
from ..users.utils import get_user_preferrence_from_cache, update_onboarding_metric
from ..users.permissions import IsSubscriptionActive
import logging

logger = logging.getLogger(__name__)


class CustomerViewset(ModelViewSet):
    permission_classes = [IsSubscriptionActive]
    serializer_class = CustomerSerializer
    queryset = Customer.objects.none()
    http_method_names = [m for m in ModelViewSet.http_method_names if m != "put"]
    search_fields = ["first_name", "last_name", "contact", "email"]

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
    
    @swagger_auto_schema(
        operation_summary="List all customers",
        operation_description="This endpoint returns a list of all customers.",
        responses={200: openapi.Response("List of customers", CustomerSerializer(many=True)),
                   401: openapi.Response("Unauthorized", openapi.Schema(type="string")),
                   403: openapi.Response("Forbidden", openapi.Schema(type="string"))}
    )

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

    @swagger_auto_schema(
        operation_summary="Retrieve a customer",
        operation_description="This endpoint returns a single customer.",
        responses={200: openapi.Response("Customer", CustomerSerializer),
                   401: openapi.Response("Unauthorized", openapi.Schema(type="string")),
                   403: openapi.Response("Forbidden", openapi.Schema(type="string")),
                   404: openapi.Response("Not Found", openapi.Schema(type="string"))}
    )
    def retrieve(self, request, *args, **kwargs):
        try:
            result = super().retrieve(request, *args, **kwargs)

            customer = self.get_object()
            currency = get_user_preferrence_from_cache(request.user.id, "currency", "USD")

            total_orders = customer.orders.filter(is_active=True).count()
            total_spent = customer.orders.filter(is_active=True).aggregate(
                        total=Sum(Coalesce("preferred_final_price", "suggested_price"))
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

    @swagger_auto_schema(
        operation_summary="Delete a customer",
        operation_description="This endpoint deletes a single customer.",
        responses={204: openapi.Response("Customer deleted successfully."),
                   401: openapi.Response("Unauthorized", openapi.Schema(type="string")),
                   403: openapi.Response("Forbidden", openapi.Schema(type="string")),
                   404: openapi.Response("Not Found", openapi.Schema(type="string"))}
    )
    def destroy(self, request, *args, **kwargs):
        """Soft delete the customer by setting is_active to False."""
        instance = self.get_object()
        instance.deactivate()
        return Response(
            {"message": "Customer deleted successfully."},
            status=status.HTTP_204_NO_CONTENT,
        )

    @swagger_auto_schema(
        operation_summary="Update a customer",
        operation_description="This endpoint updates a single customer.",
        responses={200: openapi.Response("Customer updated successfully."),
                   401: openapi.Response("Unauthorized", openapi.Schema(type="string")),
                   403: openapi.Response("Forbidden", openapi.Schema(type="string")),
                   404: openapi.Response("Not Found", openapi.Schema(type="string"))}
    )
    def partial_update(self, request, *args, **kwargs):
        """Update the customer."""
        return super().partial_update(request, *args, **kwargs)
    

    @swagger_auto_schema(
        operation_summary="Create a customer",
        operation_description="This endpoint creates a new customer.",
        responses={201: openapi.Response("Customer created successfully."),
                   401: openapi.Response("Unauthorized", openapi.Schema(type="string")),
                   403: openapi.Response("Forbidden", openapi.Schema(type="string")),
                   404: openapi.Response("Not Found", openapi.Schema(type="string"))}
    )
    def create(self, request, *args, **kwargs):
        """Create a new customer."""
        response = super().create(request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED:
            update_onboarding_metric(request.user, "has_added_customer")
        return response
