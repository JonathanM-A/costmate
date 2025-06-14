from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.conf import settings


User = get_user_model()


class Command(BaseCommand):
    help = "Initialize the system with migrations and superuser"

    def handle(self, *args, **options):
        self.stdout.write("Making migrations...")
        call_command("makemigrations")

        self.stdout.write("Running migrations...")
        call_command("migrate")

        self.stdout.write("Creating superuser...")
        self.create_superuser()

        self.stdout.write(self.style.SUCCESS("System initialized successfully!"))

    def create_superuser(self):
        # Check if superuser already exists
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write(f'Superuser already exists.')
            return

        # Create superuser
        User.objects.create_superuser(
            email=settings.ADMIN_EMAIL,
            password=settings.ADMIN_PASSWORD,
            first_name="Admin",
            last_name="User",
        )  # type: ignore
        self.stdout.write(f'Superuser created successfully!')
