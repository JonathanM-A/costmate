import smtplib
import ssl
from django.conf import settings
import environ
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

env = environ.Env()
env.read_env(".env", overwrite=True)


class SMTPHealthCheckView(APIView):
    """
    A simple health check view to verify that the application is running.
    """

    def get(self, request, *args, **kwargs):
        # Fetching values using django-environ syntax
        host = env("EMAIL_HOST")
        port = env.int("EMAIL_PORT")
        user = env("EMAIL_HOST_USER")
        password = env("EMAIL_HOST_PASSWORD")
        use_tls = env.bool("EMAIL_USE_TLS")

        print(f"Testing connection to: {host}:{port}")
        print(f"Authenticated as: {user}")
        print("-" * 30)

        try:
            # Create a secure SSL context
            context = ssl.create_default_context()

            # Connect to the server
            server = smtplib.SMTP(host, port, timeout=10)
            print("✅ 1. Physical connection established.")

            if use_tls:
                server.starttls(context=context)
                print("✅ 2. TLS Handshake successful.")

            server.login(user, password)
            print("✅ 3. Authentication successful!")

            server.quit()
            print("-" * 30)
            return Response({"message": "🎉 SUCCESS: Your SMTP settings are working perfectly."}, status=status.HTTP_200_OK)

        except smtplib.SMTPAuthenticationError:
            return Response({"message": "❌ ERROR: Authentication failed. Check your Gmail App Password."}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return Response({"message": f"❌ ERROR: Connection failed: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)