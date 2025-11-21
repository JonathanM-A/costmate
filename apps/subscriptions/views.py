import stripe
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import Subscription

User = get_user_model()
stripe.api_key = settings.STRIPE_SECRET_KEY


class CreateSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, version):
        tier_key = request.data.get("tier")

        if tier_key not in settings.TIER_PLAN_MAPPING:
            return Response(
                {"error": "Invalid subscription tier."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        plan_id = settings.TIER_PLAN_MAPPING[tier_key]

        if (
            hasattr(user, "subscription")
            and user.subscription.tier == tier_key
            and user.subscription.is_active
        ):
            return Response(
                {"message": f"You are already subscribed to the {tier_key} plan."},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            customer_id = user.stripe_customer_id
            if not customer_id:
                customer = stripe.Customer.create(
                    email=user.email,
                    name=f"{user.first_name} {user.last_name}",
                )
                user.stripe_customer_id = customer.id
                user.save()

            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{"price": plan_id}],
                expand=["latest_invoice.payment_intent"],
            )

            Subscription.objects.update_or_create(
                user=user,
                defaults={
                    "stripe_subscription_id": subscription.id,
                    "tier": tier_key,
                    "is_active": True,
                    "start_date": timezone.now(),
                    "end_date": None,
                },
            )

            return Response(
                {
                    "message": "Subscription created successfully.",
                    "subscription_id": subscription.id,
                },
                status=status.HTTP_201_CREATED,
            )
        except stripe.StripeError as e:
            return Response(
                {"error": f"Stripe error: {e.user_message}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as e:
            return Response(
                {"error": f"An unexpected error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )