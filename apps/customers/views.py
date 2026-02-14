from djmoney.money import Money
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db.models import Sum, Count, Q, Avg, Prefetch
from django.db.models.functions import Coalesce
from rest_framework.response import Response
from rest_framework import status
from rest_framework.viewsets import ModelViewSet
from .serializers import Customer, CustomerSerializer, CustomerListSerializer
from ..orders.models import Order, OrderProduct
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

        queryset = base_queryset.select_related("created_by").order_by("-created_at")

        if self.action == "list":
            queryset = queryset.annotate(
                total_orders=Count("orders", filter=Q(orders__is_active=True)),
                order_value=Sum(
                    Coalesce(
                        "orders__preferred_final_price", "orders__suggested_price"
                    ),
                    filter=Q(orders__is_active=True),
                ),
                average_order_value=Avg(
                    Coalesce(
                        "orders__preferred_final_price", "orders__suggested_price"
                    ),
                ),
            )
        else:
            queryset = queryset.prefetch_related(
                Prefetch(
                    "orders",
                    queryset=Order.objects.filter(is_active=True).prefetch_related(
                        Prefetch(
                            "order_products",
                            queryset=OrderProduct.objects.select_related("product"),
                        )
                    ),
                )
            )

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    @swagger_auto_schema(
        operation_summary="List all customers",
        operation_description="This endpoint returns a list of all customers.",
        responses={
            200: openapi.Response("List of customers", CustomerSerializer(many=True)),
            401: openapi.Response("Unauthorized", openapi.Schema(type="string")),
            403: openapi.Response("Forbidden", openapi.Schema(type="string")),
        },
    )
    def list(self, request, *args, **kwargs):
        self.serializer_class = CustomerListSerializer
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
        responses={
            200: openapi.Response("Customer", CustomerSerializer),
            401: openapi.Response("Unauthorized", openapi.Schema(type="string")),
            403: openapi.Response("Forbidden", openapi.Schema(type="string")),
            404: openapi.Response("Not Found", openapi.Schema(type="string")),
        },
    )
    def retrieve(self, request, *args, **kwargs):
        try:
            customer = self.get_object()
            serializer = self.get_serializer(customer)
            currency = get_user_preferrence_from_cache(
                request.user.id, "currency", "USD"
            )

            order_stats = customer.orders.filter(is_active=True).aggregate(
                total_orders=Count("id"),
                total_spent=Sum(Coalesce("preferred_final_price", "suggested_price")),
            )

            total_orders = order_stats["total_orders"] or 0
            total_spent_value = order_stats["total_spent"] or 0

            avg_order_value = str(
                Money(
                    total_spent_value / total_orders if total_orders > 0 else 0,
                    currency,
                )
            )
            total_spent = str(Money(total_spent_value, currency))

            stats = {
                "total_orders": total_orders,
                "total_spent": total_spent,
                "avg_order_value": avg_order_value,
            }

            data = serializer.data
            data["stats"] = stats

            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error retrieving customer: {str(e)}")
            return Response(
                {"error": "An error occurred while retrieving the customer."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @swagger_auto_schema(
        operation_summary="Delete a customer",
        operation_description="This endpoint deletes a single customer.",
        responses={
            204: openapi.Response("Customer deleted successfully."),
            401: openapi.Response("Unauthorized", openapi.Schema(type="string")),
            403: openapi.Response("Forbidden", openapi.Schema(type="string")),
            404: openapi.Response("Not Found", openapi.Schema(type="string")),
        },
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
        responses={
            200: openapi.Response("Customer updated successfully."),
            401: openapi.Response("Unauthorized", openapi.Schema(type="string")),
            403: openapi.Response("Forbidden", openapi.Schema(type="string")),
            404: openapi.Response("Not Found", openapi.Schema(type="string")),
        },
    )
    def partial_update(self, request, *args, **kwargs):
        """Update the customer."""
        return super().partial_update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Create a customer",
        operation_description="This endpoint creates a new customer.",
        responses={
            201: openapi.Response("Customer created successfully."),
            401: openapi.Response("Unauthorized", openapi.Schema(type="string")),
            403: openapi.Response("Forbidden", openapi.Schema(type="string")),
            404: openapi.Response("Not Found", openapi.Schema(type="string")),
        },
    )
    def create(self, request, *args, **kwargs):
        """Create a new customer."""
        response = super().create(request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED:
            update_onboarding_metric(request.user, "has_added_customer")
        return response
