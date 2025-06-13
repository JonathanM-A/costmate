import os
import django
from django.core.management import call_command

def init_django():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
    django.setup()

def initialize_system():
    # Make migrations
    call_command('makemigrations')

    # Run migrations
    call_command('migrate')
    
    # Create superuser
    call_command('create_superuser')

if __name__ == '__main__':
    init_django()
    initialize_system()