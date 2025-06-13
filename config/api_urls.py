from django.urls import path, include


urlpatterns = [
    path("", include("apps.users.urls")),
    path("", include("apps.customers.urls")),
    path("", include("apps.inventory.urls")),
    path("", include("apps.recipes.urls")),
]