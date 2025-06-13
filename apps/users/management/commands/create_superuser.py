from django.core.management.base import BaseCommand
from django.conf import settings
from apps.users.models import User

class Command(BaseCommand):
    help = 'Creates a superuser if none exists'

    def handle(self, *args, **options):
        if not User.objects.filter(is_superuser=True).exists():
            try:
                User.objects.create_superuser( # type: ignore
                    email=settings.ADMIN_EMAIL,
                    password=settings.ADMIN_PASSWORD,
                    first_name='Admin',
                    last_name='User'
                )
                self.stdout.write(self.style.SUCCESS('Superuser created successfully'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed to create superuser: {str(e)}'))
        else:
            self.stdout.write(self.style.WARNING('Superuser already exists'))