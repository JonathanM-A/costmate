import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from decimal import Decimal
from ..common.models import BaseModel
from ..inventory.models import InventoryItem

User = get_user_model()


class RecipeCategory(BaseModel):
    name = models.CharField(max_length=100, blank=False)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, blank=False, related_name="recipe_categories"
    )

    class Meta:  # type: ignore
        verbose_name_plural = "Recipe Categories"
        unique_together = ["name", "created_by"]
        ordering = ["name"]
    
    def __str__(self):
        return self.name


class Recipe(BaseModel):
    name = models.CharField(max_length=100, blank=False)
    category = models.ForeignKey(
        RecipeCategory,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="recipes",
    )
    inventory_items = models.ManyToManyField(
        InventoryItem, through="RecipeInventory", related_name="recipes"
    )
    inventory_items_cost = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal(0.00),
        validators=[MinValueValidator(0)],
    )
    labour_time = models.DurationField(
        null=True,
        blank=True,
        help_text="Format in POST: PT{hours}H{minutes}M or HH:MM:SS",
    )
    labour_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(0)],
        help_text="Rate per hour",
    )
    labour_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(0)],
        help_text="Total labour cost",
    )
    packaging_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(0)],
        help_text="Cost of packaging per unit",
    )
    overhead_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(0)],
        help_text="Overhead cost per unit",
    )
    profit_margin = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(0)],
        help_text="Margin percentage",
    )
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal(0.00),
        validators=[MinValueValidator(0)],
        help_text="Calculated cost price",
        null=True
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal(0.00),
        validators=[MinValueValidator(0)],
        help_text="Calculated selling price",
    )
    is_draft = models.BooleanField(
        default=False, help_text="Indicates if the recipe is a draft"
    )
    instructions = models.TextField(
        blank=True,
        null=True,
        help_text="Instructions for preparing the recipe",
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, blank=False, related_name="recipes"
    )

    # Sharing fields
    is_public = models.BooleanField(default=False)
    share_token = models.UUIDField(unique=True, editable=False, null=True)
    share_enabled = models.BooleanField(default=False)

    def regenerate_share_token(self):
        self.share_token = uuid.uuid4()
        self.save()

    def get_shareable_link(self, request):
        if self.share_token is None:
            return None
        return request.build_absolute_uri(f"api/v1/shared-recipe/{self.share_token}/")

    class Meta: # type: ignore
        unique_together = ["name", "created_by"]
        ordering = ["name"]

    def calculate_cost(self):
        """
        Calculate and update inventory_items_cost, cost_price, and selling_price.
        Should be called after the Recipe and its RecipeInventory items are saved.
        """
        if self.labour_time and self.labour_rate:
            self.labour_cost = (
                Decimal(self.labour_time.total_seconds() / 3600) * self.labour_rate
            )
        if self.inventory_items_cost:
            self.cost_price = (
                self.inventory_items_cost
                + self.labour_cost
                + self.packaging_cost
                + self.overhead_cost
            )
            self.selling_price = self.cost_price / (
                1 - (self.profit_margin / Decimal(100))
            )
        else:
            self.cost_price = 0
            self.selling_price = 0

        self.save()

    def __str__(self):
        return self.name


class RecipeInventory(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, blank=False, related_name="ingredients"
    )
    inventory_item = models.ForeignKey(
        InventoryItem, on_delete=models.CASCADE, related_name="recipe_inventory"
    )
    quantity = models.DecimalField(
        max_digits=10, decimal_places=3, validators=[MinValueValidator(0)], blank=False
    )
    cost = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal(0.00),
        validators=[MinValueValidator(0)],
    )
    suggested_cost = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal(0.00),
        validators=[MinValueValidator(0)],
        help_text="Suggested cost if not available from inventory",
    )

    class Meta:
        verbose_name_plural = "Recipe Inventory"
