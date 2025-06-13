from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RecipeViewset

router = DefaultRouter()
router.register(r"recipe", RecipeViewset, basename="recipe")

urlpatterns = [
    path("", include(router.urls))
]