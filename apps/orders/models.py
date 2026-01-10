from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from decimal import Decimal
from uuid import uuid4
from ..common.models import BaseModel
from ..customers.models import Customer
from ..recipes.models import Recipe
from ..users.utils import get_user_preferrence_from_cache

User = get_user_model()


class Order(BaseModel):
    order_no = models.CharField(unique=True, null=True, max_length=10)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="orders"
    )
    recipes = models.ManyToManyField(
        Recipe, through="OrderRecipe", related_name="orders"
    )
    total_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    profit_percentage = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal(0.00)
    )
    profit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    delivery_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        default="pending",
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="orders", blank=False
    )

    def calculate_costs(self):
        """
        Calculate the total value of the order based on the associated recipes.
        """
        user = self.created_by
        tax_rate = get_user_preferrence_from_cache(
            user.id, "tax_rate", default=Decimal("00.00")
        )
        for order_recipe in self.order_recipes.all():
            order_recipe.save()
        self.total_value = sum(
            order_recipe.line_value for order_recipe in self.order_recipes.all()
        )
        total_cost_price = sum(
            order_recipe.line_cost_price for order_recipe in self.order_recipes.all()
        )
        self.profit = self.total_value - total_cost_price
        self.profit_percentage = (
            (self.profit / total_cost_price * 100)
            if total_cost_price > 0
            else Decimal(0.00)
        )
        self.tax_amount = (self.total_value * Decimal(tax_rate) / Decimal(100)).quantize(
            Decimal("0.01")
        )

    def save(self, *args, **kwargs):
        """
        Override save method to calculate total_value before saving.
        """
        if not self.order_no:
            last_order = Order.objects.order_by("created_at").last()
            if last_order:
                last_order_no = int(last_order.order_no.split("-")[-1])
                self.order_no = f"ORD-{last_order_no + 1:05d}"
            else:
                self.order_no = "ORD-00001"
        self.calculate_costs()
        super().save(*args, **kwargs)


class OrderRecipe(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, unique=True)
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="order_recipes"
    )
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name="order_recipes"
    )
    quantity = models.PositiveIntegerField(default=1)
    line_cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    line_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    class Meta:
        unique_together = ("order", "recipe")

    def calculate_price(self):
        """
        Calculate the total price for this order recipe based on the quantity and price per unit.
        """
        self.line_value = self.recipe.selling_price * self.quantity
        self.line_cost_price = self.recipe.cost_price * self.quantity

    def save(self, *args, **kwargs):
        """
        Override save method to calculate line_value before saving.
        """
        self.calculate_price()
        super().save(*args, **kwargs)

    def update_inventory(self, user):
        """
        Update the inventory based on the quantity change.
        This method should be called when the order recipe is created or updated.
        """
        recipe_ingredients = self.recipe.ingredients.all()
        for ingredient in recipe_ingredients:
            inventory = ingredient.inventory_item.inventory.get(created_by=user)
            inventory.quantity -= ingredient.quantity * self.quantity
            inventory.save()
