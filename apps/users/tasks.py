import requests
from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.conf import settings
from .models import UserPreferences
from ..subscriptions.models import Subscription
from logging import getLogger

User = get_user_model()
logger = getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def create_user_preferences(self, user_id):
    try:
        user = User.objects.get(id=user_id)
        UserPreferences.objects.create(user=user)
    except IntegrityError as e:
        logger.error(f"IntegrityError while creating preferences for user {user_id}: {e}")
        self.retry(exc=e)
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} does not exist.")
        self.retry(exc=Exception("User does not exist"))
    except Exception as e:
        logger.error(f"Unexpected error while creating preferences for user {user_id}: {e}")
        self.retry(exc=e)

# @shared_task(bind=True, max_retries=3, default_retry_delay=60)
# def create_user_subscription(self, user_id):
#     try:
#         user = User.objects.get(id=user_id)
#         Subscription.objects.create(user=user, plan=settings.DEFAULT_SUBSCRIPTION_PLAN)
#     except IntegrityError as e:
#         logger.error(f"IntegrityError while creating subscription for user {user_id}: {e}")
#         self.retry(exc=e)
#     except User.DoesNotExist:
#         logger.error(f"User with id {user_id} does not exist.")
#         self.retry(exc=Exception("User does not exist"))
#     except Exception as e:
#         logger.error(f"Unexpected error while creating subscription for user {user_id}: {e}")
#         self.retry(exc=e)
