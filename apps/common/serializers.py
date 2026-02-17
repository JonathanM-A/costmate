from rest_framework import serializers


class RegionSerializer(serializers.Serializer):
    """Serializer for region/state/province data"""
    name = serializers.CharField()
    code = serializers.CharField()


class CountrySerializer(serializers.Serializer):
    """Serializer for country data"""
    name = serializers.CharField()
    code = serializers.CharField()
    regions = RegionSerializer(many=True, required=False)
