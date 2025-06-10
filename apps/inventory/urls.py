from django.urls import path, include
from rest_framework import routers
from .views import (
    InventoryItemView,
    SupplierViewset,
    InventoryView,
    InventoryHistoryView,
)

router = routers.DefaultRouter()
router.register("supplier", SupplierViewset, basename="supplier")
router.register(r"inventory-stock", InventoryView, basename="inventory-stock")

urlpatterns = [
    path("inventory-items", InventoryItemView.as_view(), name="inventory_items"),
    path("inventory-history", InventoryHistoryView.as_view(), name="inventory_history"),
    path("", include(router.urls)),
]
