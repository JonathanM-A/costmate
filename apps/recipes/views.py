from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from .serializers import (
    RecipeSerializer,
    RecipeDetailSerializer,
    Recipe,
    RecipeCategorySerializer,
    RecipeCategory,
)


class RecipeViewset(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Recipe.objects.none()
    serializer_class = RecipeSerializer
    http_method_names = ["get", "post", "patch", "delete"]
    search_fields = ["name"]
    filter_fields = ["category"]

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
