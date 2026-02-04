import stripe
import logging
from datetime import datetime, timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.conf import settings
from apps.subscriptions.models import Subscription
from .tasks import create_user_preferences, create_onboarding_metrics, send_welcome_email

User = get_user_model()
logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


@receiver(post_save, sender=User)
def create_related_models(sender, instance, created, **kwargs):
    if created and not instance.is_superuser:
        create_user_preferences(instance.id)  # type: ignore
        create_onboarding_metrics(instance.id)  # type: ignore
        send_welcome_email.delay(instance.id)  # type: ignore
        # create_trial_subscription(instance)


def create_trial_subscription(user):
    """Create a Stripe customer and trial subscription for a new user."""
    try:
        logger.info(f"Creating trial subscription for user {user.id}")
        # Create Stripe customer
        customer = stripe.Customer.create(
            email=user.email,
            name=f"{user.first_name} {user.last_name}",
            metadata={"user_id": str(user.id)},
        )

        # Save stripe_customer_id to user
        user.stripe_customer_id = customer.id
        user.has_used_free_trial = True
        user.save(update_fields=["stripe_customer_id", "has_used_free_trial"])

        # Get the default price ID
        default_tier = settings.DEFAULT_SUBSCRIPTION_PLAN
        price_id = settings.TIER_PLAN_MAPPING.get(default_tier)

        if not price_id:
            logger.error(f"No price ID found for default tier: {default_tier}")
            return

        # Create subscription with trial (no card required)
        stripe_subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": price_id}],
            trial_period_days=settings.TRIAL_PERIOD_DAYS,
            payment_settings={
                "save_default_payment_method": "on_subscription",
            },
            trial_settings={
                "end_behavior": {"missing_payment_method": "pause"},
            },
            metadata={
                "user_id": str(user.id),
                "product_tier": default_tier,
            },
        )

        # Create local Subscription record
        subscription_item = stripe_subscription["items"]["data"][0]
        current_sub_start = datetime.fromtimestamp(
            subscription_item["current_period_start"], tz=timezone.utc
        )
        current_sub_end = datetime.fromtimestamp(
            subscription_item["current_period_end"], tz=timezone.utc
        )

        Subscription.objects.create(
            user=user,
            tier=default_tier,
            subscription_code=stripe_subscription.id,
            current_sub_start=current_sub_start,
            current_sub_end=current_sub_end,
            is_active=True,
        )

        logger.info(f"Trial subscription created for user {user.id}")

    except stripe.StripeError as e:
        logger.error(f"Stripe error creating trial subscription for user {user.id}: {e}")
    except Exception as e:
        logger.error(f"Error creating trial subscription for user {user.id}: {e}")

