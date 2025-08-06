from django.db import models
from ..common.models import BaseModel
from ..users.models import User


class Customer(BaseModel):
    """Customer model to store customer information."""
    
    first_name = models.CharField(max_length=50, blank=False)
    last_name = models.CharField(max_length=50, blank=False)
    contact = models.CharField(max_length=15, blank=False)
    email = models.EmailField(null=True, blank=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="customers"
    )

    class Meta:  # type: ignore
        ordering = ["first_name", "last_name"]
        unique_together = ["created_by", "contact"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.contact})"
