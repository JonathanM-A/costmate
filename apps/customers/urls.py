from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomerViewset

router = DefaultRouter()
router.register(r"customers", CustomerViewset, basename="customer")

app_name = "customers"

urlpatterns = [
    path("", include(router.urls)),
]