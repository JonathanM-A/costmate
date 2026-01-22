from django.conf import settings
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied


class SubscriptionException(PermissionDenied):
    """Custom exception for subscription-related permission denials."""
    status_code = 402
    default_detail = "A subscription is required to perform this action."
    default_code = "subscription_required"

class IsSubscriptionActive(permissions.BasePermission):
    """
    Custom permission to only allow access to users with an active subscription.
    """
    
    message = "Your subscription is inactive. Please renew to perform this action."

    def has_permission(self, request, view):
        """
        Allows POST/PUT/PATCH/DELETE requests only if user has an active subscription.
        """

        if not request.user or not request.user.is_authenticated:
            return False
        
        if not getattr(settings, 'SUBSCRIPTION_LIVE', False):
            return True
        
        if request.method in permissions.SAFE_METHODS:
            return True
        
        if hasattr(request.user, 'subscription') and request.user.subscription.is_active:
            return True
        raise SubscriptionException()