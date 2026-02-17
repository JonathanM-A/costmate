from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import pycountry
from .serializers import CountrySerializer, RegionSerializer


class CountryListView(APIView):
    """
    API endpoint that returns a list of all countries.
    Optional query parameter: include_regions=true to include subdivisions
    """

    def get(self, request, version):
        include_regions = request.query_params.get('include_regions', 'false').lower() == 'true'

        countries = []
        for country in pycountry.countries:
            country_data = {
                'name': country.name,
                'code': country.alpha_2,
            }

            if include_regions:
                # Get subdivisions (states/provinces/regions) for this country
                subdivisions = pycountry.subdivisions.get(country_code=country.alpha_2)
                regions = [
                    {
                        'name': subdivision.name,
                        'code': subdivision.code
                    }
                    for subdivision in subdivisions
                ]
                country_data['regions'] = regions

            countries.append(country_data)

        # Sort by country name
        countries.sort(key=lambda x: x['name'])

        serializer = CountrySerializer(countries, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CountryDetailView(APIView):
    """
    API endpoint that returns a specific country with its regions/subdivisions
    """

    def get(self, request, version, country_code):
        try:
            country = pycountry.countries.get(alpha_2=country_code.upper())
            if not country:
                return Response(
                    {'error': 'Country not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Get subdivisions for this country
            subdivisions = pycountry.subdivisions.get(country_code=country.alpha_2)
            regions = [
                {
                    'name': subdivision.name,
                    'code': subdivision.code
                }
                for subdivision in subdivisions
            ]

            country_data = {
                'name': country.name,
                'code': country.alpha_2,
                'regions': sorted(regions, key=lambda x: x['name'])
            }

            serializer = CountrySerializer(country_data)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
