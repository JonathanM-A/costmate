import stripe
from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from .models import Business, UserPreferences, OnboardingMetrics
from logging import getLogger

User = get_user_model()
stripe.api_key = settings.STRIPE_SECRET_KEY
logger = getLogger(__name__)

DEFAULT_OVERHEAD_NAMES = [
    "Rent",
    "Electricity",
    "Gas",
    "Water",
    "Waste Removal",
    "Internet",
    "Pest Control",
]


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def create_default_overheads(self, user_id):
    """Create default overhead entries for a new user."""
    from apps.orders.models import Overhead

    retry_info = f" (Attempt {self.request.retries + 1} of {self.max_retries})"

    try:
        user = User.objects.get(id=user_id)
        overheads_to_create = [
            Overhead(name=name, created_by=user) for name in DEFAULT_OVERHEAD_NAMES
        ]
        Overhead.objects.bulk_create(overheads_to_create, ignore_conflicts=True)
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} does not exist.")
        self.retry(exc=Exception("User does not exist"))
    except Exception as e:
        logger.error(
            f"Error creating default overheads for user {user_id}: {e}{retry_info}"
        )
        self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def create_business(self, user_id):
    retry_info = f" (Attempt {self.request.retries + 1} of {self.max_retries})"
    try:
        user = User.objects.get(id=user_id)
        Business.objects.create(user=user)
    except IntegrityError as e:
        logger.error(
            f"IntegrityError while creating business for user {user_id}: {e}{retry_info}"
        )
        self.retry(exc=e)
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} does not exist.")
        self.retry(exc=Exception("User does not exist"))
    except Exception as e:
        logger.error(
            f"Unexpected error while creating business for user {user_id}: {e}{retry_info}"
        )
        self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def create_user_preferences(self, user_id):
    retry_info = f" (Attempt {self.request.retries + 1} of {self.max_retries})"
    try:
        user = User.objects.get(id=user_id)
        UserPreferences.objects.create(user=user)
    except IntegrityError as e:
        logger.error(
            f"IntegrityError while creating preferences for user {user_id}: {e}{retry_info}"
        )
        self.retry(exc=e)
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} does not exist.")
        self.retry(exc=Exception("User does not exist"))
    except Exception as e:
        logger.error(
            f"Unexpected error while creating preferences for user {user_id}: {e}{retry_info}"
        )
        self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def create_onboarding_metrics(self, user_id):
    retry_info = f" (Attempt {self.request.retries + 1} of {self.max_retries})"
    try:
        user = User.objects.get(id=user_id)
        OnboardingMetrics.objects.create(user=user)
    except IntegrityError as e:
        logger.error(
            f"IntegrityError while creating onboarding metrics for user {user_id}: {e}{retry_info}"
        )
        self.retry(exc=e)
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} does not exist.")
        self.retry(exc=Exception("User does not exist"))
    except Exception as e:
        logger.error(
            f"Unexpected error while creating onboarding metrics for user {user_id}: {e}{retry_info}"
        )
        self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_welcome_email(self, user_id):
    """Send welcome email to newly registered user."""
    retry_info = f" (Attempt {self.request.retries + 1} of {self.max_retries})"
    try:
        user = User.objects.get(id=user_id)

        context = {
            "user": user,
            "first_name": user.first_name,
        }

        html_content = render_to_string("emails/welcome.html", context)

        subject = "Welcome to CostNav!"
        from_email = settings.DEFAULT_FROM_EMAIL
        to_email = user.email

        email = EmailMultiAlternatives(subject, "", from_email, [to_email])
        email.attach_alternative(html_content, "text/html")
        email.send()
        
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} does not exist.")
        self.retry(exc=Exception("User does not exist"))
    except Exception as e:
        logger.error(f"Error sending welcome email to user {user_id}: {e}{retry_info}")
        self.retry(exc=e)
