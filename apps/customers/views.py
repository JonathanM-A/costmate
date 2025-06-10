from rest_framework.response import Response
from rest_framework import status
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from .serializers import Customer, CustomerSerializer


class CustomerViewset(ModelViewSet):
    permission_classes=[IsAuthenticated]
    serializer_class=CustomerSerializer
    queryset = Customer.objects.none()
    http_method_names = [
        m for m in ModelViewSet.http_method_names
    ]
    filterset_fields = ["customer_type", "is_discount_eligible"]
    search_fields = ["name", "contact", "email"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if user.is_authenticated:
            if user.is_superuser:
                # Superusers can see all customers
                return Customer.objects.all()
            return Customer.objects.all()
        return Customer.objects.none()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def destroy(self, request, *args, **kwargs):
        """Soft delete the customer by setting is_active to False."""
        instance = self.get_object()
        instance.deactivate()
        instance.save()
        return Response(
            {"message": "Customer deleted successfully."},
            status=status.HTTP_204_NO_CONTENT
        )
