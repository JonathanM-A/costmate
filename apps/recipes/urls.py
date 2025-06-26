from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RecipeViewset, RecipeCategoryViewset

router = DefaultRouter()
router.register(r"recipe", RecipeViewset, basename="recipe")
router.register(r"recipe-category", RecipeCategoryViewset, basename="recipe-category")


urlpatterns = [
    path("", include(router.urls))
]