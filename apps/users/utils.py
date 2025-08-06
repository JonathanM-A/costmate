from django.conf import settings
from django.core.cache import cache

def get_preferences_cache_key(user_id, version=settings.REST_FRAMEWORK["DEFAULT_VERSION"]):
    """
    Generate a cache key for user preferences based on user ID.
    
    Args:
        user_id (uuid): The ID of the user.
        action (str): The action type, default is "detail".
    
    Returns:
        str: A cache key formatted as 'user_preferences_<user_id>_<version>'.
    """
    return f'user_preferences_{user_id}_{version}'


def get_user_preferrence_from_cache(user_id, preference_type, default):
    """
    Get a preferrence for a user from the cache.

    Args:
        user_id (uuid): The ID of the user.
        preference_type (str): The type of preference to retrieve, e.g., "currency".
    
    Returns:
        str: The preferred currency of the user, or None if not set.
    """
    cache_key = get_preferences_cache_key(user_id)
    preferences = cache.get(cache_key)
    if preferences is None:
        return default
    return preferences.get(preference_type, default)

    