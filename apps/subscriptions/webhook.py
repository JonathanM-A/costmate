import stripe
from datetime import datetime, timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import status
from .models import Subscription
from .tasks import deactivate_expired_subscriptions
import logging

User = get_user_model()
logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


def update_user_subscription(stripe_customer_id, mark_trial_used=False, **kwargs):
    """Update or create a Subscription record for the user."""

    try:
        user = User.objects.get(stripe_customer_id=stripe_customer_id)
    except User.DoesNotExist:
        logger.info(f"User with Stripe Customer ID {stripe_customer_id} does not exist.")
        return

    if mark_trial_used and not user.has_used_free_trial:
        user.has_used_free_trial = True
        user.save(update_fields=['has_used_free_trial'])

    subscription, created = Subscription.objects.update_or_create(user=user, defaults=kwargs)
    logger.info(
        f"Subscription created: {created}"
    )


@csrf_exempt
@require_POST
def stripe_webhook(request, version):
    """Handle Stripe webhooks for subscription events."""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        logger.info("Verifying Stripe webhook signature.")
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        return HttpResponse(status=status.HTTP_400_BAD_REQUEST)
    except stripe.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        return HttpResponse(status=status.HTTP_400_BAD_REQUEST)

    # Handle the event
    if event["type"] == "customer.subscription.created":
        try:
            session = event["data"]["object"]

            subscription_id = session.get("id")
            customer_id = session.get("customer")

            data = session.get("items", {}).get("data", [])[0]
            plan_id = data.get("plan").get("id")

            current_sub_start = datetime.fromtimestamp(
                data.get("current_period_start"), tz=timezone.utc
            )
            end_date = datetime.fromtimestamp(
                data.get("current_period_end"), tz=timezone.utc
            )

            product_tier = None
            for k, v in settings.TIER_PLAN_MAPPING.items():
                if v == plan_id:
                    product_tier = k
                    break
            
            # Check if this subscription has a trial period
            has_trial = session.get("trial_start") is not None

            update_user_subscription(
                stripe_customer_id=customer_id,
                mark_trial_used=has_trial,
                subscription_code=subscription_id,
                tier=product_tier,
                current_sub_start=current_sub_start,
                current_sub_end=end_date,
                is_active=True,
            )
        except Exception as e:
            logger.error(f"An error occured while creating subscription {e}")

    elif event["type"] == "invoice.payment_succeeded":
        session = event["data"]["object"]

        logger.debug(
            f"Processing invoice.payment_suceeded for session ID: {session.get('id')}"
        )

        customer_id = session.get("customer")
        current_sub_start = datetime.fromtimestamp(
            session.get("period_start"), tz=timezone.utc
        )
        end_date = datetime.fromtimestamp(session.get("period_end"), tz=timezone.utc)

        update_user_subscription(
            stripe_customer_id=customer_id,
            current_sub_start=current_sub_start,
            current_sub_end=end_date,
            is_active=True,
        )
    
    elif event["type"] == "customer.subscription.deleted":
        session = event["object"]
        subscription_id = session.get("customer")
        customer_id = session.get("customer")

        update_user_subscription(
            stripe_customer_id=customer_id,
            is_cancelled=True
        )
        logger.info(f"Subscription {subscription_id} for Customer with Stripe ID {customer_id} ended.")



    elif event["type"] == "customer.subscription.updated":
        session = event["data"]["object"]
        logger.debug(
            f"Processing customer.subscription.updated for session ID: {session.get('id')}"
        )

        customer_id = session.get("customer")
        subscription_id = session.get("id")

        try:
            if session.get("cancel_at_period_end"):
                logger.info(
                    f"Subscription {session.get('id')} is set to cancel at period end."
                )
                cancel_at_time = datetime.fromtimestamp(
                    session.get("cancel_at"), tz=timezone.utc
                )

                if customer_id and subscription_id:
                    update_user_subscription(
                        stripe_customer_id=customer_id,
                        is_cancelled=True
                    )

                    logger.info(f"Subscription {subscription_id} marked as inactive.")
            else:
                logger.info(
                    f"Subscription {session.get("id")} is being upgraded"
                )

                data = session.get("items", {}).get("data", [])[0]
                plan_id = session.get("plan").get("id")

                current_sub_start = datetime.fromtimestamp(
                data.get("current_period_start"), tz=timezone.utc
                )
                end_date = datetime.fromtimestamp(
                data.get("current_period_end"), tz=timezone.utc
                )

                product_tier = None
                for k, v in settings.TIER_PLAN_MAPPING.items():
                    if v == plan_id:
                        product_tier = k
                        break
                
                update_user_subscription(
                    stripe_customer_id=customer_id,
                    subscription_code=subscription_id,
                    tier=product_tier,
                    current_sub_start=current_sub_start,
                    current_sub_end=end_date,
                    is_active=True,
                )

        except Exception as e:
            logger.error(f"Error processing subscription update: {str(e)}")

    return HttpResponse(status=status.HTTP_200_OK)
