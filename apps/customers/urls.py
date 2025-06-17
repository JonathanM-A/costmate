from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomerViewset, CustomerTypeViewset

router = DefaultRouter()
router.register(r"customers", CustomerViewset, basename="customer")
router.register(r"customer-types", CustomerTypeViewset, basename="customer-types")
urlpatterns = [
    path("", include(router.urls)),
]