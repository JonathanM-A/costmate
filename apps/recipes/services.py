from django.db import transaction
from django.db.models import (
    OuterRef,
    Subquery,
    F,
    Sum,
    Max,
    Avg,
    Case,
    When,
    Value,
    Q,
    IntegerField,
    DecimalField,
    ExpressionWrapper,
)
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from djmoney.money import Money
from .models import Recipe, RecipeInventory
from ..inventory.models import Inventory, InventoryItem
from ..inventory.services import InventoryUnitService
from ..users.utils import get_user_preferrence_from_cache
from ..products.models import ProductRecipes
from ..products.services import ProductService
from ..orders.models import OrderProduct


class RecipeService:
    @classmethod
    def create_recipe(cls, user, validated_data):
        ingredients = validated_data.pop("ingredients")

        # Set defaults
        validated_data.setdefault(
            "labour_rate",
            get_user_preferrence_from_cache(user.id, "labour_rate", 20.00),
        )

        with transaction.atomic():
            # Creating recipe
            recipe = Recipe.objects.create(created_by=user, **validated_data)

            # Creating RecipeInventory
            recipe_inventories = cls._bulk_create_ingredients(recipe, ingredients)

            item_ids = {ri.inventory_item for ri in recipe_inventories}

            # Calculating costs for RecipeInventory
            cls._bulk_update_recipe_inventory_costs(item_ids, user)

            recipe.refresh_from_db()
            recipe.calculate_cost()
            return recipe

    @classmethod
    def update_recipe(cls, instance, validated_data):
        ingredients = validated_data.pop("ingredients", None)

        with transaction.atomic():
            # Update recipe
            update_fields = []
            for field, value in validated_data.items():
                setattr(instance, field, value)
                update_fields.append(field)
            instance.save(update_fields=update_fields)

            if ingredients is not None:
                recipe_inventories = cls._bulk_replace_ingredients(
                    instance, ingredients
                )

                item_ids = {ri.inventory_item.id for ri in recipe_inventories}

                cls._bulk_update_recipe_inventory_costs(
                    item_ids, user=instance.created_by
                )

                instance.refresh_from_db()
                instance.calculate_cost()

            # Recalculate costs for products that use this recipe
            ProductService.recalculate_products_for_recipe(instance.id)

            return instance

    @staticmethod
    def _bulk_create_ingredients(recipe, ingredients):
        """Create all recipe ingredients"""

        uncreated_recipe_inventories = []

        for  ing in ingredients:
            quantity = ing["quantity"]
            unit = ing.get("unit")

            inventory_item_unit = InventoryItem.objects.filter(id=ing["inventory_item_id"]).values_list("unit", flat=True).first()
            if unit:
                InventoryUnitService.validate_unit_compatibility(
                    inventory_item_unit, unit
                )
                converted_quantity = InventoryUnitService.convert_quantity(
                    inventory_item_unit, unit, quantity
                )
                quantity = converted_quantity
            uncreated_recipe_inventories.append(
                RecipeInventory(
                    recipe=recipe,
                    inventory_item_id=ing["inventory_item_id"],
                    quantity=quantity,
                    cost=Decimal("0.00"),
                    suggested_cost=ing.get("suggested_cost", Decimal("0.00")),
                )
            )

        recipe_inventories = RecipeInventory.objects.bulk_create(
            uncreated_recipe_inventories
        )
        
        return recipe_inventories

    @staticmethod
    def _bulk_replace_ingredients(recipe, ingredients):
        """Atomically replace all ingredients"""
        RecipeInventory.objects.filter(recipe=recipe).delete()

        recipe_inventories = RecipeInventory.objects.bulk_create(
            [
                RecipeInventory(
                    recipe=recipe,
                    inventory_item_id=ing["inventory_item_id"],
                    quantity=ing["quantity"],
                    cost=Decimal("0.00"),
                    suggested_cost=ing.get("suggested_cost", Decimal("0.00")),
                )
                for ing in ingredients
            ]
        )
        return recipe_inventories

    @staticmethod
    def _bulk_update_recipe_inventory_costs(item_ids, user):

        inventories = Inventory.objects.filter(
            created_by=user, inventory_item=OuterRef("inventory_item_id")
        )

        ris = RecipeInventory.objects.filter(
            inventory_item_id__in=item_ids, recipe__created_by=user
        )

        # Use Coalesce to default cost_per_unit to 0 when the Subquery returns NULL
        cost_subquery = Subquery(inventories.values("cost_per_unit")[:1])
        ris.update(cost=F("quantity") * Coalesce(cost_subquery, Value(Decimal("0.00"))))

        updated = ris.filter(Q(cost=Decimal("0.00")) & Q(suggested_cost__gt=Decimal("0.00"))).update(
            cost=F("suggested_cost")
        )
        

        affected_recipe_ids = list(ris.values_list("recipe_id", flat=True).distinct())

        if affected_recipe_ids:
            Recipe.objects.filter(id__in=affected_recipe_ids).update(
                inventory_items_cost=Subquery(
                    RecipeInventory.objects.filter(recipe_id=OuterRef("id"))
                    .values("recipe_id")
                    .annotate(sum_cost=Sum("cost"))
                    .values("sum_cost")[:1]
                ),
            )

            Recipe.objects.filter(id__in=affected_recipe_ids).update(
                total_cost=F("inventory_items_cost") + F("labour_cost")
            )

            for recipe_id in affected_recipe_ids:
                ProductService.recalculate_products_for_recipe(recipe_id)


class RecipeAnalyticsService:
    @staticmethod
    def get_analytics(recipe, user, currency):
        now = timezone.now()
        current_month_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        prev_month_end = current_month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        six_months_back_month = now.month - 6
        six_months_back_year = now.year
        if six_months_back_month <= 0:
            six_months_back_month += 12
            six_months_back_year -= 1
        six_months_ago = now.replace(
            year=six_months_back_year,
            month=six_months_back_month,
            day=1, hour=0, minute=0, second=0, microsecond=0,
        )

        recipe_cost_val = Value(
            recipe.total_cost,
            output_field=DecimalField(max_digits=20, decimal_places=6),
        )
        _hundred = Value(Decimal('100'), output_field=DecimalField(max_digits=5, decimal_places=2))
        _one = Value(Decimal('1'), output_field=DecimalField(max_digits=3, decimal_places=2))
        _pm = F('order__profit_margin')

        # Expression factories — fresh objects per use to avoid query compilation issues
        def _bake():
            return ExpressionWrapper(
                F('quantity') * F('product__product_recipes__quantity'),
                output_field=IntegerField(),
            )

        def _revenue():
            return ExpressionWrapper(
                F('quantity') * F('product__product_recipes__quantity')
                * recipe_cost_val * (_one + _pm / _hundred),
                output_field=DecimalField(max_digits=20, decimal_places=6),
            )

        def _profit():
            return ExpressionWrapper(
                F('quantity') * F('product__product_recipes__quantity')
                * recipe_cost_val * _pm / _hundred,
                output_field=DecimalField(max_digits=20, decimal_places=6),
            )

        op_qs = OrderProduct.objects.filter(
            order__created_by=user,
            order__status='completed',
            product__product_recipes__recipe=recipe,
        )

        # Q1: All-time base stats + monthly change in a single aggregate
        base = op_qs.aggregate(
            total_bakes=Sum(_bake()),
            total_revenue=Sum(_revenue()),
            total_profit=Sum(_profit()),
            avg_margin=Avg('order__profit_margin'),
            last_baked=Max('order__created_at'),
            current_month_bakes=Sum(
                Case(
                    When(order__created_at__gte=current_month_start, then=_bake()),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            prev_month_bakes=Sum(
                Case(
                    When(
                        order__created_at__gte=prev_month_start,
                        order__created_at__lt=current_month_start,
                        then=_bake(),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            current_month_revenue=Sum(
                Case(
                    When(order__created_at__gte=current_month_start, then=_revenue()),
                    default=Value(Decimal('0')),
                    output_field=DecimalField(max_digits=20, decimal_places=6),
                )
            ),
            prev_month_revenue=Sum(
                Case(
                    When(
                        order__created_at__gte=prev_month_start,
                        order__created_at__lt=current_month_start,
                        then=_revenue(),
                    ),
                    default=Value(Decimal('0')),
                    output_field=DecimalField(max_digits=20, decimal_places=6),
                )
            ),
        )

        total_bakes = int(base['total_bakes'] or 0)
        total_revenue = base['total_revenue'] or Decimal('0')
        total_profit = base['total_profit'] or Decimal('0')
        this_avg_margin = float(base['avg_margin'] or 0)
        last_baked_dt = base['last_baked']
        current_bakes = int(base['current_month_bakes'] or 0)
        prev_bakes = int(base['prev_month_bakes'] or 0)
        current_revenue = base['current_month_revenue'] or Decimal('0')
        prev_revenue = base['prev_month_revenue'] or Decimal('0')

        # Q2: Products using this recipe
        products_count = ProductRecipes.objects.filter(
            recipe=recipe,
            product__is_active=True,
            product__created_by=user,
        ).count()

        # Q3: Monthly trend — last 6 months, grouped by month
        monthly_trend_qs = (
            op_qs.filter(order__created_at__gte=six_months_ago)
            .annotate(month=TruncMonth('order__created_at'))
            .values('month')
            .annotate(
                bake_count=Sum(_bake()),
                revenue=Sum(_revenue()),
            )
            .order_by('month')
        )
        monthly_trend = [
            {
                'month': row['month'].strftime('%b'),
                'year': row['month'].year,
                'bake_count': int(row['bake_count'] or 0),
                'revenue': str(Money(row['revenue'] or Decimal('0'), currency)),
            }
            for row in monthly_trend_qs
        ]

        # Q4: All recipes' metrics for ranking in one grouped query.
        # Uses ppr.cost (= recipe.total_cost × recipe_qty, maintained by service layer)
        # to avoid an extra join to the recipe table per recipe.
        _ppr_cost = F('product__product_recipes__cost')
        all_recipe_metrics = list(
            OrderProduct.objects.filter(
                order__created_by=user,
                order__status='completed',
            )
            .values(recipe_pk=F('product__product_recipes__recipe'))
            .annotate(
                bake_count=Sum(
                    ExpressionWrapper(
                        F('quantity') * F('product__product_recipes__quantity'),
                        output_field=IntegerField(),
                    )
                ),
                total_revenue=Sum(
                    ExpressionWrapper(
                        F('quantity') * _ppr_cost * (_one + _pm / _hundred),
                        output_field=DecimalField(max_digits=20, decimal_places=6),
                    )
                ),
                avg_margin=Avg('order__profit_margin'),
            )
        )

        popularity_rank = revenue_rank = margin_rank = 1
        this_revenue_float = float(total_revenue)
        recipe_id_str = str(recipe.id)
        for row in all_recipe_metrics:
            if row['recipe_pk'] is None or str(row['recipe_pk']) == recipe_id_str:
                continue
            if int(row['bake_count'] or 0) > total_bakes:
                popularity_rank += 1
            if float(row['total_revenue'] or 0) > this_revenue_float:
                revenue_rank += 1
            if float(row['avg_margin'] or 0) > this_avg_margin:
                margin_rank += 1

        # Q5: Total active non-draft recipe count for this user
        total_recipes = Recipe.objects.filter(
            created_by=user, is_active=True, is_draft=False,
        ).count()

        # Derived values
        bakes_monthly_change = current_bakes - prev_bakes
        if prev_revenue > 0:
            revenue_pct_change = round(
                float((current_revenue - prev_revenue) / prev_revenue * 100)
            )
        else:
            revenue_pct_change = 0

        avg_profit_per_unit = (
            total_profit / total_bakes if total_bakes > 0 else Decimal('0')
        )
        margin_pct = round(this_avg_margin)

        last_baked_date = last_baked_dt.date() if last_baked_dt else None
        days_since = (now.date() - last_baked_date).days if last_baked_date else None

        return {
            'overview': {
                'times_baked': total_bakes,
                'products_count': products_count,
                'total_profit': str(Money(total_profit, currency)),
            },
            'monthly_trend': monthly_trend,
            'analytics_cards': {
                'popularity': {'rank': popularity_rank, 'total_recipes': total_recipes},
                'margin': {
                    'rank': margin_rank,
                    'margin_percentage': str(margin_pct),
                },
                'revenue': {'rank': revenue_rank},
            },
            'financial_overview': {
                'times_baked': {
                    'total': total_bakes,
                    'monthly_change': bakes_monthly_change,
                },
                'total_revenue': {
                    'amount': str(Money(total_revenue, currency)),
                    'monthly_change_percentage': revenue_pct_change,
                },
                'avg_profit_per_unit': str(Money(avg_profit_per_unit, currency)),
                'last_baked': {
                    'date': last_baked_date,  # raw date, formatted in view
                    'days_since': days_since,
                },
            },
        }
