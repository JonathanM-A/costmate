import stripe
from datetime import datetime, timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import status
from .models import Subscription
import logging

User = get_user_model()
logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


def update_user_subscription(
    stripe_customer_id,
    subscription_id,
    tier,
    is_active,
    current_sub_start=None,
    current_sub_end=None,
):
    """Update or create a Subscription record for the user."""
    try:
        user = User.objects.get(stripe_customer_id=stripe_customer_id)
    except User.DoesNotExist:
        return

    Subscription.objects.update_or_create(
        user=user,
        defaults={
            "tier": tier,
            "subscription_code": subscription_id,
            "current_sub_start": current_sub_start,
            "current_sub_end": current_sub_end,
            "is_active": is_active,
        },
    )


@csrf_exempt
@require_POST
def stripe_webhook(request, version):
    """Handle Stripe webhooks for subscription events."""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        logger.debug("Verifying Stripe webhook signature.")
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        return HttpResponse(status=status.HTTP_400_BAD_REQUEST)
    except stripe.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        return HttpResponse(status=status.HTTP_400_BAD_REQUEST)

    # Handle the event
    if event["type"] == "customer.subscription.created":
        session = event["data"]["object"]
        logger.debug(
            f"Processing customer.subscription.created for session ID: {session.get('id')}"
        )

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

        subscription = stripe.Subscription.retrieve(subscription_id)

        start_date = datetime.fromtimestamp(subscription.start_date, tz=timezone.utc)

        update_user_subscription(
            stripe_customer_id=customer_id,
            subscription_id=subscription_id,
            tier=product_tier,
            current_sub_start=current_sub_start,
            current_sub_end=end_date,
            is_active=True,
        )
        logger.info(
            f"Subscription created for user with stripe ID {customer_id} with subscription ID {subscription_id}"
        )

    # elif event["type"] == "invoice.payment_succeeded":
    #     session = event["data"]["object"]
    #     logger.debug(
    #         f"Processing invoice.payment_suceeded for session ID: {session.get('id')}"
    #     )

    elif event["type"] == "customer.subscription.deleted":
        session = event["data"]["object"]
        logger.debug(
            f"Processing customer.subscription.deleted for session ID: {session.get('id')}"
        )

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

        subscription = stripe.Subscription.retrieve(subscription_id)

        start_date = datetime.fromtimestamp(subscription.start_date, tz=timezone.utc)

        update_user_subscription(
            stripe_customer_id=customer_id,
            subscription_id=subscription_id,
            tier=product_tier,
            current_sub_start=current_sub_start,
            current_sub_end=end_date,
            is_active=True,
        )

        try:
            
            logger.info(f"Subscription {subscription_id} marked as inactive.")
        except Subscription.DoesNotExist:
            logger.warning(f"Subscription record with ID {subscription_id} not found.")

    return HttpResponse(status=status.HTTP_200_OK)
