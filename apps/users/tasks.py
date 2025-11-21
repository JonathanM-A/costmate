import stripe
from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.conf import settings
from .models import UserPreferences
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
def create_stripe_customer(self, user_id):
    retry_info = f" (Attempt {self.request.retries + 1} of {self.max_retries})"

    try:
        user = User.objects.get(id=user_id)

        if user.stripe_customer_id:  # type: ignore
            logger.info(
                f"User {user_id} already has a Stripe customer ID: {user.stripe_customer_id}"  # type: ignore
            )

        if not user.stripe_customer_id:  # type: ignore
            logger.info(f"Creating Stripe customer for user {user_id}...")
            customer = stripe.Customer.create(
                email=user.email,
                name=f"{user.first_name} {user.last_name}",
            )
            updated_count = User.objects.filter(
                id=user_id, stripe_customer_id__isnull=True
            ).update(stripe_customer_id=customer.id)

            if updated_count == 1:
                logger.info(
                    f"Successfully created Stripe customer {customer.id} for user {user_id}"
                )
            else:
                logger.warning(
                    f"Stripe customer {customer.id} for user {user_id} was not saved due to concurrent update{retry_info}"
                )
                raise self.retry(exc=Exception("Concurrent update detected"))

    except User.DoesNotExist:
        logger.error(f"User with id {user_id} does not exist.")
    except stripe.StripeError as e:
        logger.error(
            f"StripeError while creating customer for user {user_id}: {e}{retry_info}"
        )
        raise self.retry(exc=e)
    except Exception as e:
        logger.error(
            f"Unexpected error while creating Stripe customer for user {user_id}: {e}{retry_info}"
        )
        raise self.retry(exc=e)
