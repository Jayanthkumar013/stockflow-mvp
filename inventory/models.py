from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, IntegerField, Value
from django.db.models.functions import Coalesce

DEFAULT_LOW_STOCK_THRESHOLD = 5


class Organization(models.Model):
    """A tenant. Every product belongs to exactly one organization."""

    name = models.CharField(max_length=200)
    default_low_stock_threshold = models.PositiveIntegerField(default=DEFAULT_LOW_STOCK_THRESHOLD)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    """Custom user linked to an organization. We use the email as the username."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, null=True, blank=True, related_name="users"
    )


class ProductQuerySet(models.QuerySet):
    def for_org(self, org):
        """The ONLY way views fetch products: always scoped to one organization."""
        return self.filter(organization=org)

    def with_stock_status(self, default_threshold):
        """Adds `effective_threshold` (product value, else org default) to each row."""
        return self.annotate(
            effective_threshold=Coalesce(
                "low_stock_threshold", Value(default_threshold), output_field=IntegerField()
            )
        )

    def low_stock(self, default_threshold):
        return self.with_stock_status(default_threshold).filter(
            quantity_on_hand__lte=F("effective_threshold")
        )


class Product(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=200)
    sku = models.CharField("SKU", max_length=64)
    description = models.TextField(blank=True)
    quantity_on_hand = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    selling_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    low_stock_threshold = models.PositiveIntegerField(
        null=True, blank=True, help_text="Leave empty to use the default from Settings."
    )
    last_stock_note = models.CharField(max_length=255, blank=True)
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "sku"], name="unique_sku_per_org"),
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"
