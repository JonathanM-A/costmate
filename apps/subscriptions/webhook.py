import json
import hmac
import hashlib
from datetime import datetime
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from rest_framework import status
from .models import Subscription

User = get_user_model()


@csrf_exempt
@require_POST
def paystack_webhook(request):
    # Verify the webhook signature
    paystack_signature = request.headers.get("X-Paystack-Signature")
    payload = request.body.decode("utf-8")

    computed_hash = hmac.new(
        key=settings.PAYSTACK_SECRET_KEY.encode("utf-8"),
        msg=payload.encode("utf-8"),
        digestmod=hashlib.sha512,
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, paystack_signature):
        return HttpResponse(
            status=status.HTTP_400_BAD_REQUEST, content="Invalid signature"
        )

    try:
        event = json.loads(payload)
        event_type = event.get("event")
        data = event.get("data", {})
        customer_code = data.get("customer", {}).get("customer_code")
        email = data.get("customer", {}).get("email")

        if not customer_code:
            return HttpResponse(
                status=status.HTTP_400_BAD_REQUEST, content="Missing customer code"
            )

        subscription_instance = Subscription.objects.select_related("user").get(
            customer_code=customer_code
        )
        if not subscription_instance:
            user = User.objects.get(email=email)
            subscription_instance = Subscription.objects.create(
                user=user,
                customer_code=customer_code,
            )

        plan_code = data.get("plan", {}).get("plan_code")

        tier_mapping = settings.TIER_PLAN_MAPPING
        new_tier = tier_mapping.get(plan_code, "starter")

        # Handle different event types

        # 1. Subscription Creation or Charge Success
        if event_type == "subscription.create" or event_type == "charge.success":
            subscription_code = data.get("subscription_code")

            if data.get("next_payment_date"):
                next_payment_date = datetime.strptime(
                    data["next_payment_date"], "%Y-%m-%d"
                ).date()
                subscription_instance.end_date = timezone.make_aware(
                    datetime.combine(next_payment_date, datetime.min.time())
                )

            subscription_instance.tier = new_tier
            subscription_instance.is_active = True
            subscription_instance.start_date = data.get("createdAt", timezone.now())
            subscription_instance.subscription_code = subscription_code
            subscription_instance.save()

        # 2. Subscription Cancellation
        elif event_type == "subscription.disable":
            subscription_instance.is_active = False
            subscription_instance.end_date = timezone.now()
            subscription_instance.tier = settings.DEFAULT_SUBSCRIPTION_PLAN
            subscription_instance.save()

        return HttpResponse(status=status.HTTP_200_OK)

    except json.JSONDecodeError:
        return HttpResponse(
            status=status.HTTP_400_BAD_REQUEST, content="Invalid payload"
        )
    except Exception as e:
        return HttpResponse(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR, content=str(e)
        )
