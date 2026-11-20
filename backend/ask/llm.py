"""The one place the LLM is called. It turns a question into a tool call.

The model never sees exception rows and never computes a number. It only
chooses between two tools (ask/tools.py) and fills in their arguments. Django
then validates those arguments and runs the query itself.

Step 9: not wired up yet. parse_intent always reports the LLM as unavailable,
and tests replace it with a mock. Step 10 adds the Anthropic call.
"""
from dataclasses import dataclass, field


class LLMUnavailable(Exception):
    """No key, network error, timeout, or the model didn't return a tool call."""


@dataclass(frozen=True)
class ToolCall:
    name: str  # "query_exceptions" | "cannot_answer" (anything else is refused)
    input: dict = field(default_factory=dict)


def parse_intent(question: str, locations: list[dict]) -> ToolCall:
    """Ask the model which tool to call for `question`.

    `locations` are the current org's locations only (RLS-scoped); they become
    the enum for `location_ids`, so the model can't even name another org's.
    """
    raise LLMUnavailable("LLM not configured yet")
