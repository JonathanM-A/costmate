import stripe
from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.conf import settings
from .models import UserPreferences, OnboardingMetrics
from logging import getLogger

User = get_user_model()
stripe.api_key = settings.STRIPE_SECRET_KEY
logger = getLogger(__name__)


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
