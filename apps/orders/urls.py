from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, OverheadViewSet

router = DefaultRouter()
router.register(r"orders", OrderViewSet, basename="orders")
router.register(r"overheads", OverheadViewSet, basename="overheads")

app_name = "orders"

urlpatterns = [
    path("", include(router.urls)),
]