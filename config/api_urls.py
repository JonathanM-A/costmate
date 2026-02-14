from django.urls import path, include


urlpatterns = [
    path("", include("apps.users.urls")),
    path("", include("apps.customers.urls")),
    path("", include("apps.inventory.urls")),
    path("", include("apps.recipes.urls")),
    path("", include("apps.products.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.dashboard.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.analytics.urls")),
    path("subscription/", include("apps.subscriptions.urls")),
    path("", include("apps.health.urls")),
    path("", include("apps.feedback.urls")),
]