import stripe
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
import logging

logger = logging.getLogger(__name__)
User = get_user_model()
stripe.api_key = settings.STRIPE_SECRET_KEY


class CreateSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, version):
        return Response({"detail": "Ready to create subscription."}, status=status.HTTP_200_OK)
    
    def post(self, request, version):
        """Create a new subscription for the authenticated user."""

        try:
            user = request.user
            tier_key = request.data.get('tier_key')
            price_id = settings.TIER_PLAN_MAPPING.get(tier_key)


            if not user.stripe_customer_id:
                # Create a new Stripe customer if not exists
                customer = stripe.Customer.create(
                    email=user.email,
                    name=f"{user.first_name} {user.last_name}"
                )
                user.stripe_customer_id = customer.id
                user.save()
            
            checkout_session = stripe.checkout.Session.create(
                customer=user.stripe_customer_id,
                payment_method_types=['card'],
                mode='subscription',
                line_items=[{
                    'price': price_id,
                    'quantity': 1,
                }],

                success_url=f"{settings.DOMAIN_NAME}/subscriptions/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{settings.DOMAIN_NAME}/subscriptions/cancel",

                metadata={
                    'user_id': str(user.id),
                    "product_tier": tier_key,
                }
            )
        
            return Response({"checkout_url": checkout_session.url}, status=status.HTTP_200_OK)
        
        except stripe.StripeError as e:
            logger.error(f"Stripe error during subscription creation: {e.user_message}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error during subscription creation: {str(e)}")
            return Response({"error": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CancelSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, version):
        """Cancel the user's active subscription."""
        try:
            user = request.user
            subscription = user.subscriptions

            if not subscription.is_active:
                return Response({"detail": "No active subscription to cancel."}, status=status.HTTP_400_BAD_REQUEST)

            stripe.Subscription.delete(subscription.subscription_code)

            return Response({"detail": "Subscription cancelled successfully."}, status=status.HTTP_200_OK)

        except stripe.StripeError as e:
            logger.error(f"Stripe error during subscription cancellation: {e.user_message}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error during subscription cancellation: {str(e)}")
            return Response({"error": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChangeSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, version):
        """Upgrade the user's subscription tier."""
        try:
            user = request.user
            new_tier_key = request.data.get('tier_key')
            new_price_id = settings.TIER_PLAN_MAPPING.get(new_tier_key)

            subscription = user.subscriptions

            if not subscription.is_active:
                return Response({"detail": "No active subscription to upgrade."}, status=status.HTTP_400_BAD_REQUEST)

            stripe_sub = stripe.Subscription.retrieve(subscription.subscription_code)
            item_id = stripe_sub['items']['data'][0].id

            stripe.Subscription.modify(
                subscription.subscription_code,
                items=[{
                    'id': item_id,
                    'price': new_price_id,
                }],
                proration_behavior='always_invoice',
            )

            return Response({"detail": "Subscription upgraded successfully."}, status=status.HTTP_200_OK)