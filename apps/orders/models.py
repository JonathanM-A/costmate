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

    # Pricing fields
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Sum of all recipe costs"
    )
    overhead = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    packaging = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    delivery_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Subtotal + Overhead + Packaging"
    )
    profit_margin = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        help_text="Profit margin percentage"
    )
    order_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Total cost + profit"
    )
    discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    discount_is_percentage = models.BooleanField(default=False)
    final_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Order price - discount"
    )
    vat_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal(7.5),
        help_text="VAT rate percentage"
    )
    vat_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    suggested_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Final price + VAT"
    )
    preferred_final_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="User-specified preferred final price"
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
        Calculate all order costs based on recipes, overhead, packaging, delivery, profit margin, discount and VAT.

        Calculation flow:
        1. Subtotal = sum of (recipe.total_cost * quantity) for all order recipes
        2. Total Cost = Subtotal + Overhead + Packaging + Delivery Cost
        3. Order Price = Total Cost * (1 + Profit Margin / 100)
        4. Discount Amount = Discount value (or Order Price * Discount / 100 if percentage)
        5. Final Price = Order Price - Discount Amount
        6. VAT Amount = Final Price * VAT Rate / 100
        7. Suggested Price = Final Price + VAT Amount
        """
        # Calculate subtotal from recipe costs
        self.subtotal = sum(
            order_recipe.line_cost for order_recipe in self.order_recipes.all()  # type: ignore
        )

        # Calculate total cost (subtotal + overhead + packaging + delivery)
        self.total_cost = self.subtotal + self.overhead + self.packaging + self.delivery_cost

        # Calculate order price with profit margin
        profit_multiplier = Decimal(1) + (self.profit_margin / Decimal(100))
        self.order_price = self.total_cost * profit_multiplier

        # Calculate discount amount
        if self.discount_is_percentage:
            discount_amount = self.order_price * (self.discount / Decimal(100))
        else:
            discount_amount = self.discount

        # Calculate final price
        self.final_price = self.order_price - discount_amount

        # Calculate VAT
        self.vat_amount = self.final_price * (self.vat_rate / Decimal(100))

        # Calculate suggested price (final price + VAT)
        self.suggested_price = self.final_price + self.vat_amount

    def check_inventory_availability(self):
        """
        Check if there is sufficient inventory to fulfill the order.
        Returns tuple: (bool: is_available, list: insufficient_items)

        insufficient_items format: [{"recipe": recipe_name, "ingredient": ingredient_name, "needed": amount, "available": amount}]
        """
        from ..inventory.models import Inventory

        insufficient_items = []

        for order_recipe in self.order_recipes.all():  # type: ignore
            recipe = order_recipe.recipe
            quantity_multiplier = order_recipe.quantity

            for recipe_inventory in recipe.ingredients.all():
                inventory_item = recipe_inventory.inventory_item
                required_quantity = recipe_inventory.quantity * quantity_multiplier

                try:
                    inventory = Inventory.objects.get(
                        inventory_item=inventory_item,
                        created_by=self.created_by
                    )
                    available_quantity = inventory.quantity

                    if available_quantity < required_quantity:
                        insufficient_items.append({
                            "recipe": recipe.name,
                            "ingredient": inventory_item.name,
                            "needed": str(required_quantity),
                            "available": str(available_quantity),
                            "unit": inventory_item.unit
                        })
                except Inventory.DoesNotExist:
                    insufficient_items.append({
                        "recipe": recipe.name,
                        "ingredient": inventory_item.name,
                        "needed": str(required_quantity),
                        "available": "0",
                        "unit": inventory_item.unit
                    })

        return (len(insufficient_items) == 0, insufficient_items)

    def save(self, *args, **kwargs):
        """
        Override save method to calculate costs and generate order number.
        """
        if not self.order_no:
            last_order = Order.objects.order_by("created_at").last()
            if last_order:
                last_order_no = int(last_order.order_no.split("-")[-1])  # type: ignore
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
    line_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Recipe total cost * quantity"
    )

    class Meta:
        unique_together = ("order", "recipe")

    def calculate_price(self):
        """
        Calculate the line cost based on recipe's total cost and quantity.
        """
        self.line_cost = self.recipe.total_cost * self.quantity

    def save(self, *args, **kwargs):
        """
        Override save method to calculate line_cost before saving.
        """
        self.calculate_price()
        super().save(*args, **kwargs)

    def update_inventory(self, user):
        """
        Update the inventory based on the quantity change.
        This method should be called when the order recipe is created or updated.
        """
        recipe_ingredients = self.recipe.ingredients.all()  # type: ignore
        for ingredient in recipe_ingredients:
            inventory = ingredient.inventory_item.inventory.get(created_by=user)
            inventory.quantity -= ingredient.quantity * self.quantity
            inventory.save()


class Overhead(BaseModel):
    name = models.CharField(max_length=100, blank=False)
    monthly_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal(0.00))],
    )
    yearly_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal(0.00))],
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="overheads", blank=False
    )

    class Meta:
        unique_together = ("name", "created_by")
