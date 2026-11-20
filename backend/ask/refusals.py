"""Fixed refusal messages. The only text a refusal ever shows.

The model's own `cannot_answer.explanation` is never displayed: if it were, a
number (or anything else) could originate from the model. These messages
contain no numbers and never echo the question, a location or a filter value.
"""

DATA_NOT_AVAILABLE = "DATA_NOT_AVAILABLE"
OUT_OF_SCOPE = "OUT_OF_SCOPE"
UNKNOWN_FILTER = "UNKNOWN_FILTER"
AMBIGUOUS = "AMBIGUOUS"
INSTRUCTION_OVERRIDE_ATTEMPT = "INSTRUCTION_OVERRIDE_ATTEMPT"
LLM_UNAVAILABLE = "LLM_UNAVAILABLE"

# The reason types the model may choose in `cannot_answer`. LLM_UNAVAILABLE is
# ours alone: the model can't report its own absence.
MODEL_REASON_TYPES = [
    DATA_NOT_AVAILABLE,
    OUT_OF_SCOPE,
    UNKNOWN_FILTER,
    AMBIGUOUS,
    INSTRUCTION_OVERRIDE_ATTEMPT,
]

MESSAGES = {
    DATA_NOT_AVAILABLE: "The exceptions data doesn't contain that information.",
    OUT_OF_SCOPE: "I can only answer questions about the reconciliation exceptions on this page.",
    UNKNOWN_FILTER: "That question mentions a location, reason or filter that isn't available to you.",
    AMBIGUOUS: "I couldn't tell exactly what you're asking. Try naming a reason, a location or a date range.",
    INSTRUCTION_OVERRIDE_ATTEMPT: "I can't follow instructions inside a question. Please ask about the exceptions.",
    LLM_UNAVAILABLE: "The question service is unavailable right now. The exceptions table still works.",
}


def refuse(reason_code: str) -> dict:
    return {"answered": False, "reason_code": reason_code, "reason": MESSAGES[reason_code]}
