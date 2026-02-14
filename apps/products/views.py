from djmoney.money import Money
from django.db.models import Count, Sum, Prefetch, Q
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework import status
from .models import Product, ProductRecipes, ProductCategory
from .serializers import (
    ProductSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductCategorySerializer,
)
from ..users.permissions import IsSubscriptionActive
from ..users.utils import get_user_preferrence_from_cache, update_onboarding_metric
import logging

logger = logging.Logger(__name__)


class ProductCategoryViewset(ModelViewSet):
    permission_classes = [IsSubscriptionActive]
    queryset = ProductCategory.objects.none()
    serializer_class = ProductCategorySerializer
    http_method_names = ["get", "post", "patch", "delete"]
    search_fields = ["name"]

    def get_queryset(self): # type: ignore
        user = self.request.user
        if not user.is_authenticated:
            return ProductCategory.objects.none()

        base_queryset = (
            ProductCategory.objects.all()
            if user.is_superuser
            else ProductCategory.objects.filter(
                Q(created_by=user) | Q(is_default=True), is_active=True
            )
        )
        return base_queryset.select_related("created_by").order_by("name")
    
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_default:
            return Response(
                {"error": "Default categories cannot be edited."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().partial_update(request, *args, **kwargs)


class ProductViewset(ModelViewSet):
    permission_classes = [IsSubscriptionActive]
    queryset = Product.objects.none()
    serializer_class = ProductSerializer
    http_method_names = ["get", "post", "patch"]
    search_fields = ["name"]
    filterset_fields = ["category__name"]

    def get_queryset(self): # type: ignore
        user = self.request.user
        if not user.is_authenticated:
            return Product.objects.none()

        base_queryset = (
            Product.objects.all()
            if user.is_superuser
            else Product.objects.filter(created_by=user, is_active=True)
        )

        return (
            base_queryset.prefetch_related(
                "recipes",
                Prefetch(
                    "product_recipes",
                    queryset=ProductRecipes.objects.select_related("recipe"),
                ),
            )
            .select_related("created_by", "category")
            .order_by("name")
        )

    def get_serializer_class(self): # type: ignore
        if self.action == "retrieve":
            return ProductDetailSerializer
        if self.action == "list":
            return ProductListSerializer
        return super().get_serializer_class()

    def create(self, request, *args, **kwargs):
        try:
            response = super().create(request, *args, **kwargs)
            if response.status_code == status.HTTP_201_CREATED:
                update_onboarding_metric(request.user, "has_created_product")
            return response
        except Exception as e:
            logger.error(f"Error creating product: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        currency = get_user_preferrence_from_cache(
            request.user.id, "currency", default="USD"
        )

        product_stats = queryset.aggregate(
            total_products=Count("id"),
            total_cost=Sum("total_cost"),
        )
        product_stats["total_cost"] = str(Money(product_stats["total_cost"] or 0, currency))

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data = {
                "products": response.data,
                "stats": product_stats,
            }
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "products": serializer.data,
            "stats": product_stats,
        }, status=status.HTTP_200_OK)
