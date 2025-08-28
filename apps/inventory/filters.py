import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import Inventory


class InventoryFilter(django_filters.FilterSet):
    """
    Custom filter to allow filtering by reorder_level
    """
    below_reorder = django_filters.BooleanFilter(field_name="below_reorder")

    class Meta:
        model = Inventory
        fields = ["below_reorder"]