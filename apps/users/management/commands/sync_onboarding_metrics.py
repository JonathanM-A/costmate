from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.users.models import OnboardingMetrics
from apps.inventory.models import Supplier, InventoryItem
from apps.recipes.models import Recipe
from apps.customers.models import Customer
from apps.orders.models import Order, Overhead

User = get_user_model()


class Command(BaseCommand):
    help = "Create OnboardingMetrics for all users and sync their completion status based on actual data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

        users = User.objects.filter(is_superuser=False, is_active=True)

        created_count = 0
        updated_count = 0

        for user in users:
            with transaction.atomic():
                # Create OnboardingMetrics if it doesn't exist
                metrics, created = OnboardingMetrics.objects.get_or_create(user=user)

                if created:
                    created_count += 1
                    self.stdout.write(f"Created OnboardingMetrics for user: {user.email}")

                # Check and update each condition
                updates = {}

                # Check has_added_supplier
                has_supplier = Supplier.objects.filter(created_by=user).exists()
                if has_supplier and not metrics.has_added_supplier:
                    updates["has_added_supplier"] = True

                # Check has_added_inventory
                has_inventory = InventoryItem.objects.filter(created_by=user).exists()
                if has_inventory and not metrics.has_added_inventory:
                    updates["has_added_inventory"] = True

                # Check has_created_recipe
                has_recipe = Recipe.objects.filter(created_by=user).exists()
                if has_recipe and not metrics.has_created_recipe:
                    updates["has_created_recipe"] = True

                # Check has_calculated_overhead
                has_overhead = Overhead.objects.filter(created_by=user).exists()
                if has_overhead and not metrics.has_calculated_overhead:
                    updates["has_calculated_overhead"] = True

                # Check has_added_customer
                has_customer = Customer.objects.filter(created_by=user).exists()
                if has_customer and not metrics.has_added_customer:
                    updates["has_added_customer"] = True

                # Check has_created_order
                has_order = Order.objects.filter(customer__created_by=user).exists()
                if has_order and not metrics.has_created_order:
                    updates["has_created_order"] = True

                # Apply updates
                if updates:
                    updated_count += 1
                    update_fields = list(updates.keys()) + ["updated_at"]

                    if dry_run:
                        self.stdout.write(
                            f"Would update user {user.email}: {list(updates.keys())}"
                        )
                    else:
                        for field, value in updates.items():
                            setattr(metrics, field, value)
                        metrics.save(update_fields=update_fields)
                        self.stdout.write(
                            f"Updated user {user.email}: {list(updates.keys())}"
                        )

        # Summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(self.style.SUCCESS("Sync Complete"))
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(f"Total users processed: {users.count()}")
        self.stdout.write(f"OnboardingMetrics created: {created_count}")
        self.stdout.write(f"OnboardingMetrics updated: {updated_count}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nThis was a dry run. Run without --dry-run to apply changes."))
