"""POST /api/ask: a plain-language question about the current org's exceptions.

    question --(LLM: intent only)--> tool call --(IntentSerializer)--> intent
             --(ORM, RLS-scoped)--> rows --(template)--> answer + record IDs

Refusals are HTTP 200 with answered=false: declining is a valid answer, not a
server error.
"""
from rest_framework.response import Response
from rest_framework.views import APIView

from recon.models import Location

from . import llm, refusals
from .query import run
from .refusals import refuse
from .serializers import IntentSerializer, QuestionSerializer, refusal_for


def _serialisable(intent: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in intent.items()}


class AskView(APIView):
    def post(self, request):
        # 1. The question itself: a non-empty string of at most 500 characters.
        q = QuestionSerializer(data=request.data if isinstance(request.data, dict) else {})
        if not q.is_valid():
            return Response(refuse(refusals.AMBIGUOUS))

        # 2. This org's locations (RLS-scoped). They become the model's enum
        #    and the serializer's allowed values.
        locations = list(Location.objects.order_by("location_id").values("location_id", "location_name"))

        # 3. The model picks a tool. It never sees any exception rows.
        try:
            call = llm.parse_intent(q.validated_data["question"], locations)
        except llm.LLMUnavailable:
            return Response(refuse(refusals.LLM_UNAVAILABLE))

        # 4. cannot_answer: our fixed message for its reason type. The model's
        #    explanation is dropped, so no model text (or number) is ever shown.
        if call.name == "cannot_answer":
            reason_type = call.input.get("reason_type") if isinstance(call.input, dict) else None
            if reason_type not in refusals.MODEL_REASON_TYPES:
                reason_type = refusals.OUT_OF_SCOPE
            return Response(refuse(reason_type))

        if call.name != "query_exceptions":
            return Response(refuse(refusals.OUT_OF_SCOPE))

        # 5. Re-validate the arguments as untrusted input.
        intent = IntentSerializer(data=call.input, location_ids=[l["location_id"] for l in locations])
        if not intent.is_valid():
            return Response(refuse(refusal_for(intent.errors)))

        # 6. Query and template. Every number comes with its record IDs.
        answer = run(intent.validated_data, locations)
        answer["intent"] = _serialisable(intent.validated_data)
        return Response(answer)
