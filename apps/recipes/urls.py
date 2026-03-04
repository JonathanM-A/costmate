from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RecipeViewset, RecipeCategoryViewset, SharedRecipeViewset, RecipeStepViewset

router = DefaultRouter()
router.register(r"recipe", RecipeViewset, basename="recipe")
router.register(r"recipe-category", RecipeCategoryViewset, basename="recipe-category")
router.register(r"recipe/shared", SharedRecipeViewset, basename="shared-recipe")

app_name = "recipes"

urlpatterns = [
    path("", include(router.urls)),
    path(
        "recipe/<uuid:recipe_pk>/steps/",
        RecipeStepViewset.as_view({"get": "list", "put": "replace_steps"}),
        name="recipe-steps",
    ),
]