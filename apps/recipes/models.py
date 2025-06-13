from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from ..common.models import BaseModel
from ..inventory.models import InventoryItem
import uuid

User = get_user_model()


class Recipe(BaseModel):
    name = models.CharField(max_length=100, unique=True, blank=False)
    inventory_items = models.ManyToManyField(
        InventoryItem, through="RecipeInventory", related_name="recipes"
    )
    labour_time = models.DurationField(
        null=True,
        blank=True,
        help_text="Format in POST: PT{hours}H{minutes}M or HH:MM:SS",
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, blank=False, related_name="recipes"
    )

    @property
    def total_cost(self):
        return sum(ri.cost for ri in self.recipeinventory_set.select_related("inventory_item")) # type: ignore


class RecipeInventory(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, blank=False)
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    quantity = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], blank=False
    )

    @property
    def cost(self):
        last_history = self.inventory_item.history.order_by("-created_at").first()  # type: ignore
        if last_history and last_history.cost_per_unit:
            return self.quantity * last_history.cost_per_unit
        return 0

    class Meta:
        verbose_name_plural = "Recipe Inventory"
