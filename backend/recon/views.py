"""Read-only API over the current org's exceptions.

None of these views filters by org. TenantMiddleware has already set
app.current_org for this request, and Postgres RLS removes every other org's
rows from every query below, including the location lookups.
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Location, ReasonCode, ReconException
from .serializers import ExceptionSerializer, LocationSerializer


def _bad_request(detail):
    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


class ExceptionListView(APIView):
    """GET /api/exceptions?reason=<code>&location=<location_id>

    Both filters are optional; empty means "all". Any other query parameter
    (org_id included) is ignored.
    """

    def get(self, request):
        qs = ReconException.objects.select_related("location").order_by("record_id", "reason_code")

        reason = request.query_params.get("reason", "")
        if reason:
            if reason not in ReasonCode.values:
                return _bad_request("Unknown reason code.")
            qs = qs.filter(reason_code=reason)

        location = request.query_params.get("location", "")
        if location:
            # RLS-scoped lookup: another org's location looks exactly like a
            # made-up one, so this neither confirms nor denies that it exists.
            # The message doesn't echo the value back.
            if not Location.objects.filter(location_id=location).exists():
                return _bad_request("Unknown location.")
            qs = qs.filter(location_id=location)

        return Response(ExceptionSerializer(qs, many=True).data)


class LocationListView(APIView):
    """GET /api/locations: options for the location filter."""

    def get(self, request):
        qs = Location.objects.order_by("location_id")
        return Response(LocationSerializer(qs, many=True).data)


class ReasonListView(APIView):
    """GET /api/reasons: every reason code with its plain-English label.

    Not tenant data: the same eight codes for everyone.
    """

    def get(self, request):
        return Response([{"code": c.value, "label": c.label} for c in ReasonCode])
