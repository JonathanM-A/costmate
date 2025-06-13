from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from .serializers import RecipeSerializer, Recipe


class RecipeViewset(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Recipe.objects.none()
    serializer_class = RecipeSerializer
    http_method_names = ["get", "post", "patch", "delete"]
    search_fields = ["name"]

    def get_queryset(self):  # type: ignore
        user = self.request.user
        if user.is_authenticated:
            if user.is_superuser:
                return Recipe.objects.all()
            return Recipe.objects.filter(created_by=user).select_related(
                "inventory_items"
            )

