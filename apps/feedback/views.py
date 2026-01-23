from django.core.mail import send_mail
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny


class FeedbackView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        feedback_text = request.data.get("text", "").strip()

        if not feedback_text:
            return Response(
                {"error": "Feedback text is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if request.user.is_authenticated:
            user = request.user
            subject = f"{user.first_name} {user.last_name} ({user.email}) - FEEDBACK"
        else:
            subject = "FEEDBACK"

        try:
            send_mail(
                subject=subject,
                message=feedback_text,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=["support@costnav.com"],
                fail_silently=False,
            )
            return Response(
                {"message": "Feedback submitted successfully."},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": "Failed to send feedback. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
