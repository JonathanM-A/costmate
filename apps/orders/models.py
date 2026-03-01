from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from decimal import Decimal
from uuid import uuid4
from ..common.models import BaseModel
from ..customers.models import Customer
from ..products.models import Product

User = get_user_model()


class Order(BaseModel):
    order_no = models.CharField(null=True, max_length=10)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="orders"
    )
    products = models.ManyToManyField(
        Product, through="OrderProduct", related_name="orders"
    )

    # Pricing fields
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Sum of all product costs"
    )
    overhead = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    overhead_is_percentage = models.BooleanField(default=False)
    packaging = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    packaging_is_percentage = models.BooleanField(default=False)
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

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("order_no", "created_by")
        indexes = [
            models.Index(fields=["created_by", "status"], name="order_user_status_idx"),
            models.Index(fields=["created_by", "delivery_date"], name="order_user_delivery_idx"),
            models.Index(fields=["created_by", "-created_at"], name="order_user_created_idx"),
        ]

    def calculate_costs(self):
        """
        Calculate all order costs based on products, overhead, packaging, delivery, profit margin, discount and VAT.

        Calculation flow:
        1. Subtotal = sum of (product.total_cost * quantity) for all order products
        2. Overhead Amount = Overhead value (or Subtotal * Overhead / 100 if percentage)
        3. Packaging Amount = Packaging value (or Subtotal * Packaging / 100 if percentage)
        4. Total Cost = Subtotal + Overhead Amount + Packaging Amount
        5. Order Price = Total Cost * (1 + Profit Margin / 100) + Delivery Cost
        6. Discount Amount = Discount value (or Order Price * Discount / 100 if percentage)
        7. Final Price = Order Price - Discount Amount
        8. VAT Amount = Final Price * VAT Rate / 100
        9. Suggested Price = Final Price + VAT Amount
        """
        # Calculate subtotal from product costs
        self.subtotal = sum(
            order_product.line_cost for order_product in self.order_products.all()  # type: ignore
        )

        # Calculate overhead amount
        if self.overhead_is_percentage:
            overhead_amount = self.subtotal * (self.overhead / Decimal(100))
        else:
            overhead_amount = self.overhead

        # Calculate packaging amount
        if self.packaging_is_percentage:
            packaging_amount = self.subtotal * (self.packaging / Decimal(100))
        else:
            packaging_amount = self.packaging

        # Calculate total cost (subtotal + overhead + packaging)
        self.total_cost = self.subtotal + overhead_amount + packaging_amount

        # Calculate order price with profit margin
        profit_multiplier = Decimal(1) + (Decimal(self.profit_margin) / Decimal(100))
        self.order_price = (self.total_cost * profit_multiplier) + self.delivery_cost

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

        insufficient_items format: [{"product": product_name, "ingredient": ingredient_name, "needed": amount, "available": amount}]
        """
        from ..inventory.models import Inventory
        from ..recipes.models import RecipeInventory
        from ..products.models import ProductRecipes

        insufficient_items = []

        # Prefetch order products with full chain: product -> product_recipes -> recipe -> ingredients
        order_products = self.order_products.select_related("product").prefetch_related(  # type: ignore
            models.Prefetch(
                "product__product_recipes",
                queryset=ProductRecipes.objects.select_related("recipe").prefetch_related(
                    models.Prefetch(
                        "recipe__ingredients",
                        queryset=RecipeInventory.objects.select_related("inventory_item"),
                    )
                ),
            )
        )

        # Build aggregated requirements: {inventory_item_id: {"quantity": total, "item": item, "products": [names]}}
        required_quantities = {}
        inventory_item_ids = set()

        for order_product in order_products:
            product = order_product.product
            order_qty = order_product.quantity

            for product_recipe in product.product_recipes.all():
                recipe_qty = product_recipe.quantity

                for recipe_inventory in product_recipe.recipe.ingredients.all():
                    inv_item_id = recipe_inventory.inventory_item_id
                    inventory_item_ids.add(inv_item_id)

                    # Total required = order_qty * recipe_qty * ingredient_qty
                    required = order_qty * recipe_qty * recipe_inventory.quantity

                    if inv_item_id in required_quantities:
                        required_quantities[inv_item_id]["quantity"] += required
                        if product.name not in required_quantities[inv_item_id]["products"]:
                            required_quantities[inv_item_id]["products"].append(product.name)
                    else:
                        required_quantities[inv_item_id] = {
                            "quantity": required,
                            "item": recipe_inventory.inventory_item,
                            "products": [product.name],
                        }

        # Fetch all relevant inventory records in one query
        inventory_map = {
            inv.inventory_item_id: inv
            for inv in Inventory.objects.filter(
                inventory_item_id__in=inventory_item_ids,
                created_by=self.created_by
            )
        }

        # Check availability
        for inv_item_id, data in required_quantities.items():
            inventory = inventory_map.get(inv_item_id)
            available_quantity = inventory.quantity if inventory else 0

            if available_quantity < data["quantity"]:
                insufficient_items.append({
                    "product": ", ".join(data["products"]),
                    "ingredient": data["item"].name,
                    "needed": str(data["quantity"]),
                    "available": str(available_quantity),
                    "unit": data["item"].unit
                })

        return (len(insufficient_items) == 0, insufficient_items)

    def save(self, *args, **kwargs):
        """
        Override save method to calculate costs and generate order number.
        """
        if not self.order_no:
            last_order = Order.objects.filter(created_by=self.created_by).order_by("created_at").last()
            if last_order:
                last_order_no = int(last_order.order_no.split("-")[-1])  # type: ignore
                self.order_no = f"ORD-{last_order_no + 1:05d}"
            else:
                self.order_no = "ORD-00001"
        self.calculate_costs()
        super().save(*args, **kwargs)


class OrderProduct(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, unique=True)
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="order_products"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="order_products"
    )
    quantity = models.PositiveIntegerField(default=1)
    line_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Product total cost * quantity"
    )

    class Meta:
        unique_together = ("order", "product")

    def calculate_price(self):
        """
        Calculate the line cost based on product's total cost and quantity.
        """
        self.line_cost = self.product.total_cost * self.quantity

    def save(self, *args, **kwargs):
        """
        Override save method to calculate line_cost before saving.
        """
        self.calculate_price()
        super().save(*args, **kwargs)

    def update_inventory(self, user):
        """
        Update inventory based on all recipe ingredients within this product.
        Traverses: Product -> ProductRecipes -> Recipe -> RecipeInventory -> Inventory
        """
        for product_recipe in self.product.product_recipes.all():
            recipe_qty = product_recipe.quantity
            for ingredient in product_recipe.recipe.ingredients.all():
                inventory = ingredient.inventory_item.inventory.get(created_by=user)
                inventory.quantity -= ingredient.quantity * recipe_qty * self.quantity
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
