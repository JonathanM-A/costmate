from django.db import models
from ..common.models import BaseModel
from ..users.models import User


class CustomerType(BaseModel):
    code = models.CharField(max_length=50, unique=True, blank=True, null=True)
    name = models.CharField(max_length=100, blank=False)
    description = models.TextField(blank=True, null=True)
    is_default = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)

    class Meta:  # type: ignore
        verbose_name = "Customer Type"
        verbose_name_plural = "Customer Types"

        ordering = ["name"]

    def __str__(self):
        return self.name


class Customer(BaseModel):
    """Customer model to store customer information."""

    name = models.CharField(max_length=100, blank=False)
    contact = models.CharField(max_length=15, blank=False)
    email = models.EmailField(null=True, blank=True)
    location_country = models.CharField(max_length=50, blank=True, null=True)
    location_city = models.CharField(max_length=50, blank=True, null=True)
    location_url = models.URLField(null=True, blank=True)
    customer_type = models.ForeignKey(CustomerType, on_delete=models.SET_NULL, null=True)
    custom_customer_type = models.CharField(max_length=50, null=True, blank=True)
    is_discount_eligible = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="customers"
    )

    class Meta:  # type: ignore
        ordering = ["name"]
        unique_together = ["created_by", "contact"]

    @property
    def display_customer_type(self):
        return (
            self.customer_type.name if self.customer_type else self.custom_customer_type
        )

    def __str__(self):
        return self.name
