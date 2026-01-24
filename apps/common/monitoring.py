"""
Sentry performance monitoring utilities.

This module provides utilities for custom performance tracking with Sentry.
Use these helpers to add custom spans for operations you want to monitor.
"""

import functools
from contextlib import contextmanager
from typing import Any, Callable, Optional

try:
    import sentry_sdk
    from sentry_sdk import start_span, start_transaction

    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False


@contextmanager
def monitor_span(
    op: str,
    description: str,
    data: Optional[dict] = None,
):
    """
    Context manager to create a custom Sentry span for performance monitoring.

    Usage:
        with monitor_span("db.query", "Fetch user orders", {"user_id": user.id}):
            orders = Order.objects.filter(user=user)

    Args:
        op: The operation type (e.g., "db.query", "http.request", "cache.get")
        description: Human-readable description of the operation
        data: Optional dictionary of additional data to attach to the span
    """
    if not SENTRY_AVAILABLE:
        yield
        return

    with start_span(op=op, description=description) as span:
        if data:
            for key, value in data.items():
                span.set_data(key, value)
        yield span


def monitor_function(
    op: str,
    description: Optional[str] = None,
):
    """
    Decorator to monitor a function's performance with Sentry.

    Usage:
        @monitor_function("business.calculation", "Calculate recipe cost")
        def calculate_recipe_cost(recipe_id):
            ...

    Args:
        op: The operation type
        description: Optional description (defaults to function name)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            desc = description or f"{func.__module__}.{func.__name__}"
            with monitor_span(op, desc):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def set_user_context(user) -> None:
    """
    Set user context for Sentry error and performance tracking.

    Usage:
        set_user_context(request.user)

    Args:
        user: Django user object
    """
    if not SENTRY_AVAILABLE:
        return

    if user and user.is_authenticated:
        sentry_sdk.set_user(
            {
                "id": str(user.id),
                "email": user.email,
            }
        )
    else:
        sentry_sdk.set_user(None)


def set_tag(key: str, value: str) -> None:
    """
    Set a custom tag for the current Sentry scope.

    Tags are searchable in Sentry and useful for filtering.

    Usage:
        set_tag("tenant", tenant.slug)
        set_tag("feature", "inventory_management")
    """
    if SENTRY_AVAILABLE:
        sentry_sdk.set_tag(key, value)


def capture_message(message: str, level: str = "info") -> None:
    """
    Capture a message to Sentry.

    Usage:
        capture_message("User exceeded API rate limit", level="warning")

    Args:
        message: The message to capture
        level: Severity level (debug, info, warning, error, fatal)
    """
    if SENTRY_AVAILABLE:
        sentry_sdk.capture_message(message, level=level)


def add_breadcrumb(
    message: str,
    category: str,
    level: str = "info",
    data: Optional[dict] = None,
) -> None:
    """
    Add a breadcrumb for debugging context.

    Breadcrumbs appear in error reports to show what happened before an error.

    Usage:
        add_breadcrumb(
            "User clicked checkout",
            category="ui.click",
            data={"cart_items": 5}
        )
    """
    if SENTRY_AVAILABLE:
        sentry_sdk.add_breadcrumb(
            message=message,
            category=category,
            level=level,
            data=data or {},
        )
