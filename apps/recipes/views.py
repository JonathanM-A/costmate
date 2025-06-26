from django.db import transaction
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework import status
from .serializers import (
    RecipeSerializer,
    Recipe,
    RecipeInventory,
    RecipeCategorySerializer,
    RecipeCategory,
)


class RecipeViewset(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Recipe.objects.none()
    serializer_class = RecipeSerializer
    http_method_names = ["get", "post", "put", "delete"]
    search_fields = ["name"]
    filter_fields = ["category"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if user.is_authenticated:
            if user.is_superuser:
                return Recipe.objects.all()
            return (
                Recipe.objects.filter(created_by=user)
                .prefetch_related("inventory_items")
                .select_related("created_by")
            )

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        ingredient_updates = request.data.get("ingredients", None)

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if ingredient_updates:
            for item in ingredient_updates:
                inventory_item_id = item.get("inventory_item_id")
                new_quantity = item.get("quantity")

                if inventory_item_id and new_quantity:
                    try:
                        recipe_inventory, created = (
                            RecipeInventory.objects.get_or_create(
                                recipe=instance,
                                inventory_item__id=inventory_item_id,
                                defaults={
                                    "quantity": new_quantity,
                                    "inventory_item_id": inventory_item_id,
                                },
                            )
                        )
                        if not created:
                            recipe_inventory.quantity = new_quantity
                            recipe_inventory.save()
                    except ValidationError as e:
                        return Response(
                            {"error": str(e)}, status=status.HTTP_400_BAD_REQUEST
                        )

        return Response(serializer.data, status=status.HTTP_200_OK)


class RecipeCategoryViewset(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = RecipeCategory.objects.none()
    serializer_class = RecipeCategorySerializer
    http_method_names = ["get", "post", "patch", "delete"]
    search_fields = ["name"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if user.is_authenticated:
            if user.is_superuser:
                return RecipeCategory.objects.all()
            return RecipeCategory.objects.filter(created_by=user).select_related(
                "created_by"
            )
