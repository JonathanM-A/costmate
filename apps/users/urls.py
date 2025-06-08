from django.urls import path
from .views import (UserRetrieveUpdateView)


urlpatterns = [
    path('profile/', UserRetrieveUpdateView.as_view(), name='user-profile'),
]