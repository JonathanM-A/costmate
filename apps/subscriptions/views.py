import requests
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import Subscription

User = get_user_model()


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
        plan_code = settings.TIER_PLAN_MAPPING[tier_key]

        if (
            hasattr(user, "subscription")
            and user.subscription.tier == tier_key
            and user.subscription.is_active
        ):
            return Response(
                {"message": f"You are already subscribed to the {tier_key} plan."},
                status=status.HTTP_409_CONFLICT,
            )
        
        url = f"{settings.PAYSTACK_BASE_URL}/transaction/initialize"

        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "email": user.email,
            "plan": plan_code,
            "amount": "10",
            "channels": ["card"],
            "reference": f"{user.id}-{tier_key}-{timezone.now().timestamp()}",
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            print(response)
            response_data = response.json()

            if response_data.get("status"):
                return Response({
                    "message": "Transaction initialized.",
                    "paystack_data": response_data["data"],
                    "access_code": response_data["data"]["access_code"]
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    "error": response_data.get("message", "Paystack initialization failed")
                }, status=status.HTTP_400_BAD_REQUEST)
        
        except requests.RequestException as e:
            return Response({"error": f"API request error: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)