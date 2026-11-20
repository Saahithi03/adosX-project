"""ask.llm with the Gemini client mocked: request shape and response handling.

No network. The live tests (test_ask_live.py) cover the real model.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.genai import errors as genai_errors

from ask import llm
from ask.tools import build_tools

ORG_A_LOCATIONS = [
    {"location_id": "LOC-101", "location_name": "Location 101"},
    {"location_id": "LOC-102", "location_name": "Location 102"},
    {"location_id": "LOC-103", "location_name": "Location 103"},
]


def response(*calls):
    """A stand-in for GenerateContentResponse: only .function_calls is read."""
    return SimpleNamespace(function_calls=list(calls) or None)


def call(name, args):
    return SimpleNamespace(name=name, args=args)


@pytest.fixture
def fake_client(mocker, settings):
    settings.GEMINI_API_KEY = "test-key-not-real"
    client = MagicMock()
    client.models.generate_content.return_value = response(call("query_exceptions", {"metric": "count"}))
    mocker.patch("ask.llm.genai.Client", return_value=client)
    return client


def sent(fake_client):
    return fake_client.models.generate_content.call_args.kwargs


# --- request shape -----------------------------------------------------------------

def test_request_shape(fake_client, settings):
    llm.parse_intent("How many at Location 103?", ORG_A_LOCATIONS)
    kwargs = sent(fake_client)
    config = kwargs["config"]

    assert kwargs["model"] == settings.ASK_MODEL
    # The brief's settings: a function call is mandatory, and temperature is 0.
    fcc = config.tool_config.function_calling_config
    assert fcc.mode == "ANY"
    assert set(fcc.allowed_function_names) == {"query_exceptions", "cannot_answer"}
    assert config.temperature == 0
    # The question is wrapped as data, and no exception rows are sent.
    assert "<question>\nHow many at Location 103?\n</question>" in kwargs["contents"]
    assert "REC-" not in kwargs["contents"] and "REC-" not in config.system_instruction


def test_only_the_users_locations_are_offered(fake_client):
    llm.parse_intent("q", ORG_A_LOCATIONS)
    declarations = sent(fake_client)["config"].tools[0].function_declarations
    query = next(d for d in declarations if d.name == "query_exceptions")
    enum = query.parameters_json_schema["properties"]["location_ids"]["items"]["enum"]
    assert enum == ["LOC-101", "LOC-102", "LOC-103"]
    assert "LOC-201" not in json.dumps(query.parameters_json_schema)


def test_missing_key_is_unavailable_without_calling(mocker, settings):
    settings.GEMINI_API_KEY = ""
    constructor = mocker.patch("ask.llm.genai.Client")
    with pytest.raises(llm.LLMUnavailable):
        llm.parse_intent("q", ORG_A_LOCATIONS)
    constructor.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        genai_errors.ClientError(400, {"error": {"message": "API key not valid", "status": "INVALID_ARGUMENT"}}),
        genai_errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}}),
        genai_errors.ServerError(503, {"error": {"message": "overloaded", "status": "UNAVAILABLE"}}),
        TimeoutError("timed out"),
        ConnectionError("network down"),
    ],
    ids=["bad-key", "quota", "server", "timeout", "network"],
)
def test_api_failures_become_unavailable(fake_client, error):
    fake_client.models.generate_content.side_effect = error
    with pytest.raises(llm.LLMUnavailable):
        llm.parse_intent("q", ORG_A_LOCATIONS)


# --- response handling ---------------------------------------------------------------

def test_function_call_is_returned_as_is():
    tool_call = llm.to_tool_call(response(call("query_exceptions", {"metric": "list", "location_ids": ["LOC-103"]})))
    assert tool_call == llm.ToolCall("query_exceptions", {"metric": "list", "location_ids": ["LOC-103"]})


def test_only_the_first_call_is_used():
    tool_call = llm.to_tool_call(
        response(call("cannot_answer", {"reason_type": "AMBIGUOUS"}), call("query_exceptions", {"metric": "count"}))
    )
    assert tool_call.name == "cannot_answer"


def test_no_function_call_is_refused():
    # e.g. a safety block: no candidates, so no function call and no text used.
    assert llm.to_tool_call(response()) == llm.ToolCall("cannot_answer", {"reason_type": "OUT_OF_SCOPE"})


def test_call_with_no_args_becomes_empty_dict():
    assert llm.to_tool_call(response(call("query_exceptions", None))) == llm.ToolCall("query_exceptions", {})


# --- schemas -------------------------------------------------------------------------

def test_schemas_are_closed_objects():
    for tool in build_tools(ORG_A_LOCATIONS):
        assert tool["parameters"]["additionalProperties"] is False


def test_org_with_no_locations_gets_no_location_filter():
    query = next(t for t in build_tools([]) if t["name"] == "query_exceptions")
    assert "location_ids" not in query["parameters"]["properties"]


def test_config_builds_for_an_org_with_no_locations():
    llm.build_config([])  # must not raise (an empty enum would be invalid)
