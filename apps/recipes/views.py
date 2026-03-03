from djmoney.money import Money
from django.db.models import Count, Q, Sum, Prefetch
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from .models import RecipeInventory
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from .serializers import (
    RecipeSerializer,
    RecipeDetailSerializer,
    Recipe,
    RecipeCategorySerializer,
    RecipeCategory,
)
from .services import RecipeAnalyticsService
from ..users.permissions import IsSubscriptionActive
from ..users.utils import get_user_preferrence_from_cache, update_onboarding_metric
from ..users.serializers import UserFormattedDate
import logging

logger = logging.Logger(__name__)


class RecipeViewset(ModelViewSet):
    permission_classes = [IsSubscriptionActive]
    queryset = Recipe.objects.none()
    serializer_class = RecipeSerializer
    http_method_names = ["get", "post", "patch", "delete"]
    search_fields = ["name"]
    filterset_fields = ["category__name", "is_draft"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if not user.is_authenticated:
            return Recipe.objects.none()

        base_queryset = (
            Recipe.objects.all()
            if user.is_superuser
            else Recipe.objects.filter(created_by=user, is_active=True)
        )

        return (
            base_queryset.prefetch_related(
                "inventory_items",
                Prefetch(
                    "ingredients",
                    queryset=RecipeInventory.objects.select_related("inventory_item"),
                ),
            )
            .select_related("created_by", "category")
            .order_by("name")
        )
    
    def get_serializer_class(self): # type: ignore
        if self.action == "retrieve":
            return RecipeDetailSerializer
        return super().get_serializer_class()
    
    def create(self, request, *args, **kwargs):
        try:
            response = super().create(request, *args, **kwargs)
            if response.status_code == status.HTTP_201_CREATED:
                update_onboarding_metric(request.user, "has_created_recipe")
            return response
        except Exception as e:
            logger.error(f"Error creating recipe: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        currency = get_user_preferrence_from_cache(
            request.user.id, "currency", default="USD"
        )

        recipe_stats = queryset.aggregate(
            total_recipes=Count("id"),
            total_drafts=Count("id", filter=Q(is_draft=True)),
            total_active=Count("id", filter=Q(is_draft=False)),
            total_cost=Sum("total_cost"),
        )
        recipe_stats["total_cost"] = str(Money(recipe_stats["total_cost"] or 0, currency))

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data = {
                "recipes": response.data,
                "stats": recipe_stats,
            }
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "recipes": serializer.data,
            "stats": recipe_stats,
        }, status=status.HTTP_200_OK)
    

    @action(detail=True, methods=["get"])
    def analytics(self, request, pk=None, **kwargs):
        recipe = self.get_object()
        currency = get_user_preferrence_from_cache(request.user.id, "currency", "USD")

        data = RecipeAnalyticsService.get_analytics(recipe, request.user, currency)

        last_baked = data["financial_overview"]["last_baked"]
        if last_baked["date"]:
            date_field = UserFormattedDate(read_only=True)
            date_field._context = {"request": request}
            last_baked["date"] = date_field.to_representation(last_baked["date"])

        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def enable_sharing(self, request, pk=None):
        recipe = self.get_object()
        recipe.share_enabled = True
        recipe.regenerate_share_token()
        recipe.save()
        return Response(
            {"shareable_link": recipe.get_shareable_link()},
            status=status.HTTP_200_OK,
        )
    
    @action(detail=True, methods=["post"])
    def disable_sharing(self, request, pk=None):
        recipe = self.get_object()
        recipe.share_enabled = False
        recipe.share_token = None
        recipe.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SharedRecipeViewset(ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    queryset = Recipe.objects.none()
    serializer_class = RecipeDetailSerializer
    lookup_field = "share_token"
    http_method_names = ["get"]

    def get_queryset(self):  # type: ignore
        return (
            Recipe.objects.filter(share_enabled=True)
            .prefetch_related(
                "inventory_items",
                Prefetch(
                    "ingredients",
                    queryset=RecipeInventory.objects.select_related("inventory_item"),
                ),
            )
            .select_related("created_by", "category")
            .order_by("name")
        )
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    def list(self, request, *args, **kwargs):
        return Response(
            {"detail": "List not allowed. Use the shareable link to access a specific recipe."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class RecipeCategoryViewset(ModelViewSet):
    permission_classes = [IsSubscriptionActive]
    queryset = RecipeCategory.objects.none()
    serializer_class = RecipeCategorySerializer
    http_method_names = ["get", "post", "patch", "delete"]
    search_fields = ["name"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if not user.is_authenticated:
            return RecipeCategory.objects.none()

        base_queryset = (
            RecipeCategory.objects.all()
            if user.is_superuser
            else RecipeCategory.objects.filter(Q(created_by=user)|Q(is_default=True), is_active=True)
        )
        return base_queryset.select_related("created_by").order_by("name")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.deactivate()
        return Response(
            {"message": "Category deleted successfully."},
            status=status.HTTP_204_NO_CONTENT,
        )
