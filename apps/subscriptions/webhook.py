import stripe
from datetime import datetime, timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import status
from .models import Subscription
from apps.notifications.models import Notification
import logging

User = get_user_model()
logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


def update_user_subscription(stripe_customer_id, mark_trial_used=False, **kwargs):
    """Update or create a Subscription record for the user."""

    try:
        user = User.objects.get(stripe_customer_id=stripe_customer_id)
    except User.DoesNotExist:
        logger.error(f"User with Stripe Customer ID {stripe_customer_id} does not exist.")
        return

    if mark_trial_used and not user.has_used_free_trial: # type: ignore
        user.has_used_free_trial = True # type: ignore
        user.save(update_fields=['has_used_free_trial'])

    Subscription.objects.update_or_create(user=user, defaults=kwargs)


@csrf_exempt
@require_POST
def stripe_webhook(request, version):
    """Handle Stripe webhooks for subscription events."""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
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
        session = event["data"]["object"]
        subscription_id = session.get("id")
        customer_id = session.get("customer")

        update_user_subscription(
            stripe_customer_id=customer_id,
            is_cancelled=True
        )
        logger.info(f"Subscription {subscription_id} for Customer with Stripe ID {customer_id} ended.")



    elif event["type"] == "customer.subscription.updated":
        session = event["data"]["object"]

        customer_id = session.get("customer")
        subscription_id = session.get("id")

        try:
            if session.get("status") in ["paused", "canceled"]:

                cancel_at_time = datetime.fromtimestamp(
                    session.get("cancel_at"), tz=timezone.utc
                )

                if customer_id and subscription_id:
                    update_user_subscription(
                        stripe_customer_id=customer_id,
                        is_cancelled=True,
                        is_active=False,
                    )
            else:
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

    elif event["type"] == "customer.subscription.trial_will_end":
        session = event["data"]["object"]
        customer_id = session.get("customer")
        trial_end = session.get("trial_end")

        try:
            user = User.objects.get(stripe_customer_id=customer_id)
            trial_end_date = datetime.fromtimestamp(trial_end, tz=timezone.utc)
            formatted_date = trial_end_date.strftime("%B %d, %Y")
            add_payment_url = f"{settings.DOMAIN_NAME}/add-payment-method"

            # Create notification
            Notification.objects.create(
                user=user,
                notification_type="TRIAL_ENDING",
                message=f"Your free trial ends on {formatted_date}. Add a payment method to continue using COSTNAV.",
                target_url=add_payment_url,
            )

            # Send email
            context = {
                "user_name": user.first_name or user.email,
                "trial_end_date": formatted_date,
                "billing_url": add_payment_url,
            }
            html_message = render_to_string("subscriptions/email/trial_ending.html", context)
            plain_message = render_to_string("subscriptions/email/trial_ending.txt", context)

            send_mail(
                subject="Your COSTNAV Trial is Ending Soon",
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )

        except User.DoesNotExist:
            logger.error(f"User with Stripe Customer ID {customer_id} not found for trial_will_end event")
        except Exception as e:
            logger.error(f"Error processing trial_will_end event: {str(e)}")

    return HttpResponse(status=status.HTTP_200_OK)
