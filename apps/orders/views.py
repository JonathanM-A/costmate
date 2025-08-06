from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from .serializers import OrderSerializer, Order


class OrderViewSet(ModelViewSet):
    queryset = Order.objects.none()
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch"]
    search_fields = ["customer__name", "order_no"]
    filter_fields = ["status", "delivery_date"]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            if user.is_superuser:
                return Order.objects.all()
            else:
                return (
                    Order.objects.filter(created_by=user)
                    .prefetch_related("recipes")
                    .select_related("customer")
                )
        return Order.objects.none()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context
    
    def partial_update(self, request, *args, **kwargs):
        raise NotImplementedError(
            "Partial update is not allowed for this viewset."
        )
    
    @action(methods=["patch"], detail=True, url_path="update-status")
    def update_status(self, request, pk=None, **kwargs):
        order = self.get_object()
        new_status = request.data.get("status")

        if new_status not in ["pending", "completed", "cancelled"]:
            return Response(
                {"detail": "Invalid status."},
                status=400
            )

        order.status = new_status
        order.save()

        serializer = self.get_serializer(order)
        return Response(serializer.data, status=200)
