from django.db.models import Q
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from .serializers import (
    Customer,
    CustomerSerializer,
    CustomerType,
    CustomerTypeSerializer,
)


class CustomerTypeViewset(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerTypeSerializer
    queryset = CustomerType.objects.none()
    http_method_names = [m for m in ModelViewSet.http_method_names if m != "put"]
    search_fields = ["name"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if user.is_authenticated:
            if user.is_superuser:
                return CustomerType.objects.all()
            return CustomerType.objects.filter(Q(created_by=user) | Q(is_default=True))
        return CustomerType.objects.none()

    def destroy(self, request, *args, **kwargs):
        """Soft delete the CustomerType"""
        instance = self.get_object()

        if instance.is_default:
            raise ValidationError({"error": "Default Customer Types cannot be deleted"})

        instance.deactivate()
        return Response(
            {"message": "Customer Type deleted successfully"},
            status=status.HTTP_204_NO_CONTENT,
        )

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.is_default:
            raise ValidationError({"error": "Default Customer Types cannot be edited"})
        
        return super().partial_update(request, *args, **kwargs)

class CustomerViewset(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerSerializer
    queryset = Customer.objects.none()
    http_method_names = [m for m in ModelViewSet.http_method_names if m != "put"]
    filterset_fields = ["customer_type", "is_discount_eligible"]
    search_fields = ["name", "contact", "email"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if user.is_authenticated:
            if user.is_superuser:
                # Superusers can see all customers
                return Customer.objects.all()
            return Customer.objects.filter(created_by=user)
        return Customer.objects.none()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def destroy(self, request, *args, **kwargs):
        """Soft delete the customer by setting is_active to False."""
        instance = self.get_object()
        instance.deactivate()
        return Response(
            {"message": "Customer deleted successfully."},
            status=status.HTTP_204_NO_CONTENT,
        )
