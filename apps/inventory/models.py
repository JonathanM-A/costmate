from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from ..common.models import BaseModel
from ..users.models import User
from django.utils import timezone
import uuid


class InventoryItem(BaseModel):
    name = models.CharField(max_length=50, unique=True)
    unit = models.CharField(max_length=20, blank=True, null=True)
    is_default = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_inventory_items",
        blank=False,
    )

    class Meta:  # type: ignore
        unique_together = ["name", "created_by"]

    def __str__(self):
        return f"{self.name} ({self.unit})" if self.unit else self.name


class Supplier(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    contact = models.CharField(max_length=20, blank=True, null=True)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_suppliers", blank=False
    )

    def __str__(self):
        return self.name


class Inventory(BaseModel):
    id = models.UUIDField(
        default=uuid.uuid4,  # Generate UUID and convert to string
        editable=False,
        primary_key=True,
        max_length=36,
    )
    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.CASCADE,
        related_name="inventory",
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,  # type: ignore
        validators=[MinValueValidator(0)],
    )
    reorder_level = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,  # type: ignore
        validators=[MinValueValidator(0)],
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_inventories", blank=False
    )

    class Meta:  # type: ignore
        verbose_name_plural = "Inventory"
        unique_together = ["inventory_item", "created_by"]

    @property
    def is_below_reorder_level(self):
        return self.quantity < self.reorder_level

    def __str__(self):
        return str(self.pk)


class InventoryHistory(BaseModel):
    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.CASCADE,
        related_name="history",
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,  # type: ignore
        validators=[MinValueValidator(0)],
    )
    is_addition = models.BooleanField(default=True)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="history",
        blank=True,
        null=True,
    )
    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    incident_date = models.DateField(blank=True, null=True, default=timezone.now)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_inventory_history",
        blank=False,
    )
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal(0.00))

    class Meta:  # type: ignore
        verbose_name_plural = "Inventory History"

    def __str__(self):
        return str(self.pk)

    def save(self, *args, **kwargs):
        if self.quantity > 0:
            self.cost_per_unit = self.cost_price/self.quantity
        super().save(*args, **kwargs)
