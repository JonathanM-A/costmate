from django.urls import path, include
from rest_framework import routers
from .views import (
    InventoryItemView,
    SupplierViewset,
    InventoryView,
    InventoryHistoryView,
    InventoryUnitView,
)

router = routers.DefaultRouter()
router.register(r"supplier", SupplierViewset, basename="supplier")
router.register(r"inventory-stock", InventoryView, basename="inventory-stock")
router.register(r"inventory-items", InventoryItemView, basename="inventory-items")
router.register(r"inventory-units", InventoryUnitView, basename="inventory-units")

app_name = "inventory"

urlpatterns = [
    path("inventory-history", InventoryHistoryView.as_view(), name="inventory_history"),
    path("", include(router.urls)),
]
