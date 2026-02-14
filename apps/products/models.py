from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth import get_user_model
from ..common.models import BaseModel
from ..recipes.models import Recipe

User = get_user_model()

class ProductCategory(BaseModel):
    name = models.CharField(max_length=255, blank=False, null=False)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="product_categories")
    is_default = models.BooleanField(default=False)

    class Meta: # type: ignore
        verbose_name_plural = "Product Categories"
        ordering = ["name"]
        unique_together = ("name", "created_by")

class Product(BaseModel):
    name = models.CharField(max_length=255, blank=False)
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, related_name="products")
    recipes = models.ManyToManyField(Recipe, related_name="products", through="ProductRecipes", blank=True, null=True)
    recipes_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    recipes_count = models.PositiveIntegerField(default=0)
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
    total_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal(0.00),
        validators=[MinValueValidator(0)],
        help_text="Total cost of the product (recipes cost + labour cost)",
    )
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="products")

    class Meta: # type: ignore
        ordering = ["name"]
        unique_together = ("name", "created_by")
    
    def calculate_costs(self):
        self.recipes_cost = sum([pr.cost for pr in self.product_recipes.all()]) # type: ignore
        self.recipes_count = self.product_recipes.count() #type: ignore
        self.labour_cost = Decimal(self.labour_time.total_seconds() / 3600) * Decimal(self.labour_rate) if self.labour_time else Decimal("0.00")
        self.total_cost = self.recipes_cost + self.labour_cost
    
    def save(self, *args, **kwargs):
        self.calculate_costs()
        super().save(*args, **kwargs)


class ProductRecipes(BaseModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="product_recipes")
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="recipe_products")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="product_recipes")

    class Meta: # type: ignore
        verbose_name = "Product Recipe"
        verbose_name_plural = "Product Recipes"
        unique_together = ("product", "recipe", "created_by")
        ordering = ["product", "recipe"]
    
    def calculate_cost(self):
        self.cost = self.quantity * self.recipe.total_cost