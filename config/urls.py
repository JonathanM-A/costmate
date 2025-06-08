"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
import debug_toolbar
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from apps.users.views import GoogleLoginCallback
from drf_yasg.generators import OpenAPISchemaGenerator


class BothHttpAndHttpsSchemaGenerator(OpenAPISchemaGenerator):
    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request, public)
        # Manually add AllAuth endpoints
        if "allauth" not in schema.paths:
            schema.paths["/accounts/login/"] = {
                "post": {
                    "tags": ["auth"],
                    "description": "AllAuth Login",
                    "responses": {
                        "200": {"description": "OK"},
                        "400": {"description": "Bad Request"},
                    },
                }
            }
        return schema
    

schema_view = get_schema_view(
    openapi.Info(
        title="My API",
        default_version="v1",
        description="CostMate API",
        terms_of_service="https://www.example.com/terms/",
        contact=openapi.Contact(email="kamajthomas@gmail.com"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    generator_class=BothHttpAndHttpsSchemaGenerator,
    permission_classes=(permissions.AllowAny,),
)


urlpatterns = [
    path("admin/", admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path(
        "accounts/social/", include("allauth.socialaccount.urls")
    ),
    path("__debug__/", include(debug_toolbar.urls)),
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path(
        "swagger<format>/", schema_view.without_ui(cache_timeout=0), name="schema-json"
    ),
    path(r'^accounts/', include('allauth.urls'), name='socialaccount_signup'),
    # path("accounts/google/login/callback/", GoogleLoginCallback.as_view(), name="google_login_callback"),
    path("auth/v1/", include(("config.auth_urls", "auth"), namespace="auth")),
    path("api/<str:version>/", include(("config.api_urls", "api"), namespace="api")),
    path("", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
]
