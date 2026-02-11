from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductViewset, ProductCategoryViewset

router = DefaultRouter()
router.register(r"product", ProductViewset, basename="product")
router.register(r"product-category", ProductCategoryViewset, basename="product-category")

app_name = "products"

urlpatterns = [
    path("", include(router.urls))
]
