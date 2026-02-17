from django.urls import path
from .views import CountryListView, CountryDetailView

app_name = "common"

urlpatterns = [
    path("countries/", CountryListView.as_view(), name="country-list"),
    path("countries/<str:country_code>/", CountryDetailView.as_view(), name="country-detail"),
]
