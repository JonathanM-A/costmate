from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from apps.users.models import Business

User = get_user_model()


class Command(BaseCommand):
    help = "Create Business records for existing users who don't have one"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

        users_without_business = User.objects.filter(
            is_superuser=False,
            is_active=True,
            business__isnull=True,
        )

        count = users_without_business.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("All users already have a Business record."))
            return

        self.stdout.write(f"Found {count} user(s) without a Business record.")

        created_count = 0
        for user in users_without_business:
            if dry_run:
                self.stdout.write(f"  Would create Business for: {user.email}")
            else:
                Business.objects.create(user=user)
                self.stdout.write(f"  Created Business for: {user.email}")
            created_count += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(self.style.SUCCESS("Complete"))
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(f"Total users processed: {created_count}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nThis was a dry run. Run without --dry-run to apply changes."))
