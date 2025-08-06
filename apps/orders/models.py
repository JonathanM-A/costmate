from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from decimal import Decimal
from uuid import uuid4
from ..common.models import BaseModel
from ..customers.models import Customer
from ..recipes.models import Recipe

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
    profit = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal(0.00))
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

    def calculate_total_value(self):
        """
        Calculate the total value of the order based on the associated recipes.
        """
        self.total_value = sum(recipe.selling_price for recipe in self.recipes.all())

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
        self.calculate_total_value()
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

    def save(self, *args, **kwargs):
        """
        Override save method to calculate line_value before saving.
        """
        self.calculate_price()
        super().save(*args, **kwargs)
