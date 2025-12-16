from djmoney.money import Money
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q, Sum, Avg
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
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
from ..users.utils import get_user_preferrence_from_cache


class RecipeViewset(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Recipe.objects.none()
    serializer_class = RecipeSerializer
    http_method_names = ["get", "post", "patch", "delete"]
    search_fields = ["name"]
    filterset_fields = ["category__name"]

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
            base_queryset.prefetch_related("inventory_items", "ingredients")
            .select_related("created_by", "category")
            .order_by("name")
        )
    
    def get_serializer_class(self):
        if self.action == "retrieve":
            return RecipeDetailSerializer
        return super().get_serializer_class()
    
    def list(self, request, *args, **kwargs):
        result = super().list(request, *args, **kwargs)
        recipe_stats = self.get_queryset().aggregate(
            total_recipes=Count("id"),
            total_drafts=Count("id", filter=Q(is_draft=True)),
            total_active=Count("id", filter=Q(is_draft=False)),
            total_cost=Sum("cost_price"),
            avg_profit_margin=Avg("profit_margin"),
        )

        currency = get_user_preferrence_from_cache(
            request.user.id, "currency", default="USD"
        )
        recipe_stats["total_cost"] = str(Money(
            recipe_stats["total_cost"] or 0, currency
        ))
        
        if not recipe_stats["avg_profit_margin"]:
            recipe_stats["avg_profit_margin"] = 0

        result.data = {
            "recipes": result.data,
            "stats": {**recipe_stats},
        }
        return Response(result.data, status=status.HTTP_200_OK)
    

    @action(detail=True, methods=["post"])
    def enable_sharing(self, request, pk=None):
        recipe = self.get_object()
        recipe.share_enabled = True
        recipe.regenerate_share_token()
        recipe.save()
        return Response(
            {"shareable_link": recipe.get_shareable_link(request)},
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
        return Recipe.objects.filter(share_enabled=True).prefetch_related(
            "inventory_items", "ingredients"
        ).select_related("created_by", "category").order_by("name")
    
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
    permission_classes = [IsAuthenticated]
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
            else RecipeCategory.objects.filter(created_by=user, is_active=True)
        )
        return (
            base_queryset.filter(created_by=user)
            .select_related("created_by")
            .order_by("name")
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.deactivate()
        return Response(
            {"message": "Category deleted successfully."},
            status=status.HTTP_204_NO_CONTENT,
        )
