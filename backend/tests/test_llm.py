"""ask.llm with the Anthropic client mocked: request shape and response handling.

No network. The live tests (test_ask_live.py) cover the real model.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import pytest

from ask import llm
from ask.tools import build_tools

ORG_A_LOCATIONS = [
    {"location_id": "LOC-101", "location_name": "Location 101"},
    {"location_id": "LOC-102", "location_name": "Location 102"},
    {"location_id": "LOC-103", "location_name": "Location 103"},
]


def response(*blocks, stop_reason="tool_use"):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


def tool_use(name, input):
    return SimpleNamespace(type="tool_use", name=name, input=input)


def text(t):
    return SimpleNamespace(type="text", text=t)


@pytest.fixture
def fake_client(mocker, settings):
    settings.ANTHROPIC_API_KEY = "test-key-not-real"
    client = MagicMock()
    client.beta.messages.create.return_value = response(tool_use("query_exceptions", {"metric": "count"}))
    mocker.patch("ask.llm.anthropic.Anthropic", return_value=client)
    return client


# --- request shape -----------------------------------------------------------------

def test_request_shape(fake_client):
    llm.parse_intent("How many at Location 103?", ORG_A_LOCATIONS)
    kwargs = fake_client.beta.messages.create.call_args.kwargs

    assert kwargs["model"] == "claude-sonnet-5-5"
    # Forced tool use and temperature are rejected by this model (DECISIONS.md).
    assert kwargs["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert "temperature" not in kwargs
    assert all(t["strict"] is True for t in kwargs["tools"])
    assert {t["name"] for t in kwargs["tools"]} == {"query_exceptions", "cannot_answer"}
    # The question is wrapped as data, and no exception rows are sent.
    content = kwargs["messages"][0]["content"]
    assert "<question>\nHow many at Location 103?\n</question>" in content
    assert "REC-" not in json.dumps(kwargs)


def test_only_the_users_locations_are_offered(fake_client):
    llm.parse_intent("q", ORG_A_LOCATIONS)
    kwargs = fake_client.beta.messages.create.call_args.kwargs
    query_tool = next(t for t in kwargs["tools"] if t["name"] == "query_exceptions")
    enum = query_tool["input_schema"]["properties"]["location_ids"]["items"]["enum"]
    assert enum == ["LOC-101", "LOC-102", "LOC-103"]
    assert "LOC-201" not in json.dumps(kwargs) and "LOC-202" not in json.dumps(kwargs)


def test_missing_key_is_unavailable_without_calling(mocker, settings):
    settings.ANTHROPIC_API_KEY = ""
    constructor = mocker.patch("ask.llm.anthropic.Anthropic")
    with pytest.raises(llm.LLMUnavailable):
        llm.parse_intent("q", ORG_A_LOCATIONS)
    constructor.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APIConnectionError(request=MagicMock()),
        anthropic.APITimeoutError(request=MagicMock()),
    ],
    ids=["connection", "timeout"],
)
def test_api_failures_become_unavailable(fake_client, error):
    fake_client.beta.messages.create.side_effect = error
    with pytest.raises(llm.LLMUnavailable):
        llm.parse_intent("q", ORG_A_LOCATIONS)


@pytest.mark.parametrize("status, cls", [(401, anthropic.AuthenticationError), (429, anthropic.RateLimitError),
                                         (500, anthropic.InternalServerError)])
def test_http_errors_become_unavailable(fake_client, status, cls):
    resp = MagicMock(status_code=status, headers={})
    fake_client.beta.messages.create.side_effect = cls("boom", response=resp, body=None)
    with pytest.raises(llm.LLMUnavailable):
        llm.parse_intent("q", ORG_A_LOCATIONS)


# --- response handling ---------------------------------------------------------------

def test_tool_call_is_returned_as_is():
    call = llm.to_tool_call(response(tool_use("query_exceptions", {"metric": "list", "location_ids": ["LOC-103"]})))
    assert call == llm.ToolCall("query_exceptions", {"metric": "list", "location_ids": ["LOC-103"]})


def test_text_before_the_tool_call_is_ignored():
    call = llm.to_tool_call(response(text("Sure! There are 500."), tool_use("cannot_answer", {"reason_type": "AMBIGUOUS"})))
    assert call.name == "cannot_answer" and "500" not in json.dumps(call.input)


def test_text_only_reply_is_refused_and_never_passed_through():
    call = llm.to_tool_call(response(text("The answer is 500."), stop_reason="end_turn"))
    assert call == llm.ToolCall("cannot_answer", {"reason_type": "OUT_OF_SCOPE"})


def test_safety_refusal_is_out_of_scope():
    call = llm.to_tool_call(response(stop_reason="refusal"))
    assert call == llm.ToolCall("cannot_answer", {"reason_type": "OUT_OF_SCOPE"})


# --- schemas stay inside what strict mode supports -----------------------------------------

def test_schemas_avoid_unsupported_strict_constraints():
    dumped = json.dumps(build_tools(ORG_A_LOCATIONS))
    for unsupported in ["maxItems", "minItems", "maxLength", "minLength", "minimum", "maximum"]:
        assert unsupported not in dumped
    for tool in build_tools(ORG_A_LOCATIONS):
        assert tool["input_schema"]["additionalProperties"] is False


def test_org_with_no_locations_gets_no_location_filter():
    query_tool = next(t for t in build_tools([]) if t["name"] == "query_exceptions")
    assert "location_ids" not in query_tool["input_schema"]["properties"]
