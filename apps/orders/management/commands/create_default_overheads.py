from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.orders.models import Overhead
from apps.users.tasks import DEFAULT_OVERHEAD_NAMES
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create default overheads for all users who don't have them"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user-id",
            type=str,
            help="Create overheads for a specific user by ID",
        )

    def handle(self, *args, **options):
        user_id = options.get("user_id")

        if user_id:
            users = User.objects.filter(id=user_id, is_superuser=False)
            if not users.exists():
                self.stdout.write(
                    self.style.ERROR(f"User with ID {user_id} not found.")
                )
                return
        else:
            users = User.objects.filter(is_superuser=False)

        total_users = users.count()
        if total_users == 0:
            self.stdout.write(self.style.WARNING("No users found."))
            return

        self.stdout.write(
            self.style.SUCCESS(f"Processing {total_users} user(s)...")
        )

        created_count = 0
        skipped_count = 0

        for user in users.iterator():
            existing_names = set(
                Overhead.objects.filter(created_by=user).values_list("name", flat=True)
            )
            overheads_to_create = [
                Overhead(name=name, created_by=user)
                for name in DEFAULT_OVERHEAD_NAMES
                if name not in existing_names
            ]

            if overheads_to_create:
                Overhead.objects.bulk_create(overheads_to_create)
                created_count += len(overheads_to_create)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Created {len(overheads_to_create)} overhead(s) for user {user.email}"
                    )
                )
            else:
                skipped_count += 1
                self.stdout.write(
                    f"- Skipped user {user.email} (already has all overheads)"
                )

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(
            self.style.SUCCESS(f"Total overheads created: {created_count}")
        )
        self.stdout.write(f"Users skipped (already complete): {skipped_count}")
        self.stdout.write("=" * 50)
