from django.conf import settings
from django.core.cache import cache
from .models import UserPreferences, OnboardingMetrics
from .serializers import UserPreferencesSerializer
import logging

logger = logging.getLogger(__name__)

def get_preferences_cache_key(user_id, version=settings.REST_FRAMEWORK["DEFAULT_VERSION"]):
    """
    Generate a cache key for user preferences based on user ID.
    
    Args:
        user_id (uuid): The ID of the user.
        version (str): The version of the API.
    
    Returns:
        str: A cache key formatted as 'user_preferences_<user_id>_<version>'.
    """
    user_id_str = str(user_id)
    return f'user_preferences_{user_id_str}_{version}'


def get_user_preferrence_from_cache(user_id, preference_type, default):
    """
    Get a preferrence for a user from the cache.

    Args:
        user_id (uuid): The ID of the user.
        preference_type (str): The type of preference to retrieve, e.g., "currency".
    
    Returns:
        str: The preferred currency of the user, or None if not set.
    """
    cache_key = get_preferences_cache_key(user_id, version=settings.REST_FRAMEWORK["DEFAULT_VERSION"])
    preferences = cache.get(cache_key)
    if not preferences:
        try:
            user_preferences = UserPreferences.objects.get(user_id=user_id)
            serializer = UserPreferencesSerializer(user_preferences)
            preferences = serializer.data
            cache.set(cache_key, preferences)
            preferences = cache.get(cache_key)
        except UserPreferences.DoesNotExist:
            return default
    return preferences.get(preference_type, default) or default


def update_onboarding_metric(user, metric_field):
    """
    Update a specific onboarding metric field to True for a user.

    Args:
        user: The user instance.
        metric_field (str): The name of the metric field to update.

    Returns:
        bool: True if the metric was updated, False otherwise.
    """
    try:
        if not hasattr(user, "onboarding_metrics"):
            return False

        metrics = user.onboarding_metrics
        if not getattr(metrics, metric_field, True):
            setattr(metrics, metric_field, True)
            metrics.save(update_fields=[metric_field, "updated_at"])
            return True
        return False
    except OnboardingMetrics.DoesNotExist:
        logger.warning(f"OnboardingMetrics not found for user {user.id}")
        return False
    except Exception as e:
        logger.error(f"Error updating onboarding metric {metric_field} for user {user.id}: {e}")
        return False
