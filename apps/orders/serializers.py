from datetime import datetime
from decimal import Decimal
from djmoney.money import Money
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from ..users.utils import get_user_preferrence_from_cache
from ..users.serializers import UserFormattedDate
from .models import Order, Customer, OrderProduct, Overhead
from ..products.models import Product


class CustomerOrderProductSerializer(serializers.ModelSerializer):
    """Lightweight serializer for product names in customer order history."""
    product_name = serializers.StringRelatedField(read_only=True, source="product")

    class Meta:
        model = OrderProduct
        fields = ["product_name"]


class CustomerOrderSerializer(serializers.ModelSerializer):
    """Lightweight serializer for customer order history display."""
    products = serializers.SerializerMethodField()
    delivery_date = UserFormattedDate(read_only=True)
    suggested_price = serializers.SerializerMethodField()
    preferred_final_price = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["id", "order_no", "products", "suggested_price", "preferred_final_price", "delivery_date", "status"]
        read_only_fields = fields

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

    def get_products(self, obj):
        order_products = getattr(obj, "prefetched_order_products", None) or obj.order_products.all()
        return [op.product.name for op in order_products]

    def get_suggested_price(self, obj):
        return str(Money(obj.suggested_price, self.currency))

    def get_preferred_final_price(self, obj):
        if obj.preferred_final_price is not None:
            return str(Money(obj.preferred_final_price, self.currency))
        return None


class OrderProductSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), write_only=True, source="product"
    )
    product_name = serializers.StringRelatedField(read_only=True, source="product")

    class Meta:
        model = OrderProduct
        exclude = ["order"]
        read_only_fields = ["id", "line_cost", "order"]

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user

        if user and "product_id" in fields:
            fields["product_id"].queryset = fields["product_id"].queryset.filter(
                Q(is_active=True) | Q(created_by=user.id)
            )
        return fields

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        if "line_cost" in representation:
            representation["line_cost"] = str(Money(representation["line_cost"], self.currency))

        return representation


class OrderSerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    products = serializers.ListField(
        child=serializers.DictField(), min_length=1, write_only=True
    )
    order_products = OrderProductSerializer(many=True, read_only=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    delivery_date = UserFormattedDate(allow_null=True, required=False)

    class Meta:
        model = Order
        exclude = ["created_at", "updated_at", "is_active"]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "status",
            "order_no",
            "subtotal",
            "total_cost",
            "order_price",
            "final_price",
            "vat_amount",
            "suggested_price",
        ]
        extra_kwargs = {
            "delivery_date": {"required": False, "allow_null": True},
            "overhead": {"required": False},
            "overhead_is_percentage": {"required": False},
            "packaging": {"required": False},
            "packaging_is_percentage": {"required": False},
            "discount": {"required": False},
            "discount_is_percentage": {"required": False},
            "profit_margin": {"required": False},
            "preferred_final_price": {"required": False, "allow_null": True},
        }

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user

        if user and "customer" in fields:
            fields["customer"].queryset = fields["customer"].queryset.filter(
                Q(is_active=True) | Q(created_by=user.id)
            )
        return fields


    def create(self, validated_data):
        from ..notifications.models import Notification
        from django.contrib.contenttypes.models import ContentType

        products = validated_data.pop("products")
        user = self.context["request"].user

        validated_data.setdefault("profit_margin", get_user_preferrence_from_cache(user.id, "profit_margin", 20.00))

        with transaction.atomic():
            order_instance = Order.objects.create(**validated_data)

            # Prefetch all products in one query to avoid N+1
            product_ids = [product_data["product_id"] for product_data in products]
            product_map = {
                str(product_obj.id): product_obj
                for product_obj in Product.objects.filter(id__in=product_ids)
            }

            order_products = [
                OrderProduct(
                    order=order_instance,
                    product_id=product_data["product_id"],
                    quantity=product_data.get("quantity", 1),
                    line_cost=product_map[product_data["product_id"]].total_cost * product_data.get("quantity", 1),
                )
                for product_data in products
            ]
            OrderProduct.objects.bulk_create(order_products)
            order_instance.save()

            # Check inventory availability and create notification if insufficient
            is_available, insufficient_items = order_instance.check_inventory_availability()
            if not is_available:
                message = f"Order {order_instance.order_no} created but insufficient inventory for: "
                for item in insufficient_items:
                    message += f"- {item['product']}: {item['ingredient']} (Need: {item['needed']}{item['unit']}, Available: {item['available']}{item['unit']})"

                Notification.objects.create(
                    user=user,
                    notification_type="INSUFFICIENT_INVENTORY",
                    message=message,
                    content_type=ContentType.objects.get_for_model(Order),
                    object_id=order_instance.id,
                )

            return order_instance

    def update(self, instance, validated_data):
        products = validated_data.pop("products", None)
        validated_data["created_by"] = self.context["request"].user

        with transaction.atomic():
            instance = super().update(instance, validated_data)

            if products is not None:
                # Delete existing order products
                instance.order_products.all().delete()

                # Prefetch all products in one query to avoid N+1
                product_ids = [product_data["product_id"] for product_data in products]
                product_map = {
                    str(product_obj.id): product_obj
                    for product_obj in Product.objects.filter(id__in=product_ids)
                }

                new_products = [
                    OrderProduct(
                        order=instance,
                        product_id=product_data["product_id"],
                        quantity=product_data.get("quantity", 1),
                        line_cost=product_map[product_data["product_id"]].total_cost * product_data.get("quantity", 1),
                    )
                    for product_data in products
                ]
                OrderProduct.objects.bulk_create(new_products)
                instance.save()

        return instance

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        money_fields = [
            "subtotal",
            "overhead",
            "packaging",
            "total_cost",
            "order_price",
            "discount",
            "final_price",
            "vat_amount",
            "suggested_price",
            "preferred_final_price",
        ]

        for field in money_fields:
            if field in representation and representation[field] is not None:
                representation[field] = str(Money(amount=representation[field], currency=self.currency))

        representation["profit_margin"] = str(instance.profit_margin) + "%"
        representation["vat_rate"] = str(instance.vat_rate) + "%"
        representation["customer"] = instance.customer.name
        return representation

class InvoiceOrderProductSerializer(serializers.ModelSerializer):
    """Serializer for line items in an invoice."""
    product_name = serializers.CharField(source="product.name", read_only=True)
    category = serializers.CharField(source="product.category.name", default=None, read_only=True)
    unit_price = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()

    class Meta:
        model = OrderProduct
        fields = ["product_name", "category", "unit_price", "quantity", "amount"]

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

    def get_unit_price(self, obj):
        profit_margin = self.context.get("profit_margin", Decimal(0))
        profit_multiplier = Decimal(1) + (profit_margin / Decimal(100))
        unit_cost = obj.line_cost / obj.quantity if obj.quantity else obj.line_cost
        unit_price = unit_cost * profit_multiplier
        return str(Money(unit_price, self.currency))

    def get_amount(self, obj):
        profit_margin = self.context.get("profit_margin", Decimal(0))
        profit_multiplier = Decimal(1) + (profit_margin / Decimal(100))
        selling_amount = obj.line_cost * profit_multiplier
        return str(Money(selling_amount, self.currency))


class InvoiceSerializer(serializers.ModelSerializer):
    """Serializer for the invoice view, matching the invoice design."""
    # Business info
    business = serializers.SerializerMethodField()
    # Customer info
    customer = serializers.SerializerMethodField()
    # Invoice metadata
    invoice_no = serializers.CharField(source="order_no", read_only=True)
    date = serializers.SerializerMethodField()
    delivery_date = UserFormattedDate(read_only=True)
    # Line items
    items = serializers.SerializerMethodField()
    # Financial summary
    subtotal = serializers.SerializerMethodField()
    service_charge = serializers.SerializerMethodField()
    discount = serializers.SerializerMethodField()
    tax = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    deposit_percentage = serializers.SerializerMethodField()
    deposit_due = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()
    invoice_footer = serializers.SerializerMethodField()
    delivery_cost = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "business",
            "customer",
            "invoice_no",
            "date",
            "delivery_date",
            "items",
            "service_charge",
            "delivery_cost",
            "subtotal",
            "discount",
            "tax",
            "total",
            "deposit_percentage",
            "deposit_due",
            "balance_due",
            "invoice_footer",
        ]

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

    def get_date(self, obj):
        today = datetime.now().date()
        date_field = UserFormattedDate(read_only=True)
        date_field.bind("date", self)
        return date_field.to_representation(today)

    def get_business(self, obj):
        business = getattr(obj.created_by, "business", None)
        if not business:
            return None
        request = self.context.get("request")
        logo_url = None
        if business.logo and request:
            logo_url = request.build_absolute_uri(business.logo.url)
        return {
            "name": business.name,
            "address": business.address,
            "logo": logo_url,
        }

    def get_customer(self, obj):
        customer = obj.customer
        return {
            "name": customer.name,
            "phone": customer.contact,
            "address": customer.address,
            "email": customer.email,
        }

    def get_items(self, obj):
        order_products = (
            getattr(obj, "prefetched_order_products", None)
            or obj.order_products.select_related("product__category").all()
        )
        context = {**self.context, "profit_margin": obj.profit_margin}
        return InvoiceOrderProductSerializer(
            order_products, many=True, context=context
        ).data

    def get_subtotal(self, obj):
        profit_multiplier = Decimal(1) + (Decimal(obj.profit_margin) / Decimal(100))
        self.subtotal = obj.total_cost * profit_multiplier
        return str(Money(self.subtotal, self.currency))

    def get_service_charge(self, obj):
        overhead_and_packaging = obj.total_cost - obj.subtotal
        if not overhead_and_packaging:
            return None
        profit_multiplier = Decimal(1) + (Decimal(obj.profit_margin) / Decimal(100))
        return str(Money(overhead_and_packaging * profit_multiplier, self.currency))
    
    def get_delivery_cost(self, obj):
        return str(Money(obj.delivery_cost, self.currency))

    def get_discount(self, obj):
        if obj.discount_is_percentage:
            discount_amount = obj.order_price * (obj.discount / Decimal("100"))
        else:
            discount_amount = obj.discount
        return str(Money(discount_amount, self.currency))

    def get_tax(self, obj):
        tax_enabled = get_user_preferrence_from_cache(
            self.context["request"].user.id, "tax_enabled", False
        )
        if not tax_enabled:
            return None
        return str(Money(obj.vat_amount, self.currency))

    def get_total(self, obj):
        return str(Money(self._get_total(obj), self.currency))

    def _get_deposit_percentage(self, obj):
        business = getattr(obj.created_by, "business", None)
        if business:
            return business.deposit_percentage
        return Decimal("0.00")

    def get_deposit_percentage(self, obj):
        return str(self._get_deposit_percentage(obj)) + "%"

    def _get_total(self, obj):
        return obj.preferred_final_price if obj.preferred_final_price is not None else obj.suggested_price

    def _get_deposit_amount(self, obj):
        deposit_pct = self._get_deposit_percentage(obj)
        return self._get_total(obj) * (deposit_pct / Decimal("100"))

    def get_deposit_due(self, obj):
        return str(Money(self._get_deposit_amount(obj), self.currency))

    def get_balance_due(self, obj):
        balance = self._get_total(obj) - self._get_deposit_amount(obj)
        return str(Money(balance, self.currency))
    
    def get_invoice_footer(self, obj):
        business = getattr(obj.created_by, "business", None)
        if business and business.invoice_footer:
            return business.invoice_footer
        return None


class OverheadSerializer(serializers.ModelSerializer):
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Overhead
        exclude = ["is_active", "created_at", "updated_at"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        return value.title()

    @property
    def currency(self):
        return get_user_preferrence_from_cache(
            self.context["request"].user.id, "currency", "USD"
        )

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["yearly_cost"] = str(
            Money(amount=instance.yearly_cost, currency=self.currency)
        )
        representation["monthly_cost"] = str(
            Money(amount=instance.monthly_cost, currency=self.currency)
        )
        return representation


class OverheadUpdateItemSerializer(serializers.Serializer):
    id = serializers.PrimaryKeyRelatedField(queryset=Overhead.objects.all())
    monthly_cost = serializers.DecimalField(max_digits=10, decimal_places=2)
    yearly_cost = serializers.DecimalField(max_digits=10, decimal_places=2)

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user
        if user and "id" in fields:
            fields["id"].queryset = fields["id"].queryset.filter(created_by=user)
        return fields


class BulkOverheadUpdateSerializer(serializers.Serializer):
    overheads = OverheadUpdateItemSerializer(many=True)

    def update(self, instance, validated_data):
        overheads_data = validated_data["overheads"]

        updated_overheads = []
        for item in overheads_data:
            overhead = item["id"]
            overhead.monthly_cost = item["monthly_cost"]
            overhead.yearly_cost = item["yearly_cost"]
            updated_overheads.append(overhead)

        with transaction.atomic():
            Overhead.objects.bulk_update(
                updated_overheads, ["monthly_cost", "yearly_cost"]
            )

        return updated_overheads