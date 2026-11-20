"""The exceptions, locations and reasons API, over HTTP, per org.

Each test logs in as ONE user. (Inside a test, requests share the test's
transaction, so an org set by one request would still be set for the next;
in production each request's SET LOCAL ends with its own transaction.)
"""
import pytest
from django.test import Client

from recon.models import ReasonCode

pytestmark = pytest.mark.django_db

ORG_A_RECORDS = ["REC-1015", "REC-1027", "REC-1042", "REC-1064", "REC-1077", "REC-1088", "REC-1999"]
ORG_B_RECORDS = ["REC-1003", "REC-1019", "REC-1050", "REC-1061"]
ITEM_KEYS = {
    "record_id", "location_id", "location_name", "reason_code",
    "reason_label", "a_amount", "b_amount", "b_entry_ids",
}


def client_for(user):
    c = Client()
    c.force_login(user)  # real session cookie: goes through TenantMiddleware
    return c


def records(resp):
    assert resp.status_code == 200, resp.content
    return [item["record_id"] for item in resp.json()]


# --- isolation over the API -------------------------------------------------------

def test_org_a_lists_its_seven(ingested, alice):
    assert records(client_for(alice).get("/api/exceptions")) == ORG_A_RECORDS


def test_org_b_lists_its_four(ingested, bob):
    assert records(client_for(bob).get("/api/exceptions")) == ORG_B_RECORDS


def test_org_a_never_sees_org_b_locations_anywhere(ingested, alice):
    c = client_for(alice)
    for url in ["/api/exceptions", "/api/locations", "/api/reasons", "/api/me",
                "/api/exceptions?location=LOC-201", "/api/exceptions?org_id=ORG-B"]:
        body = c.get(url).content.decode()
        assert "LOC-201" not in body and "LOC-202" not in body, url
        assert "ORG-B" not in body, url


def test_rec_1077_shown_at_org_a_branch_without_b_details(ingested, alice):
    [item] = [i for i in client_for(alice).get("/api/exceptions").json() if i["record_id"] == "REC-1077"]
    assert item["location_id"] == "LOC-102"
    assert item["reason_code"] == "LOCATION_MISMATCH"
    assert set(item) == ITEM_KEYS  # no b_location_id, no org_id


def test_org_id_query_param_is_ignored(ingested, alice):
    assert records(client_for(alice).get("/api/exceptions?org_id=ORG-B")) == ORG_A_RECORDS


@pytest.mark.parametrize("url", ["/api/exceptions", "/api/locations", "/api/reasons"])
def test_anonymous_is_refused(ingested, url):
    assert Client().get(url).status_code == 403


# --- item shape ------------------------------------------------------------------

def test_item_shape_matches_spec(ingested, alice):
    [item] = [i for i in client_for(alice).get("/api/exceptions").json() if i["record_id"] == "REC-1088"]
    assert item == {
        "record_id": "REC-1088",
        "location_id": "LOC-103",
        "location_name": "Location 103",
        "reason_code": "TAX_NOT_RECORDED",
        "reason_label": "Accounts recorded the pre-tax amount only",
        "a_amount": "138948.30",
        "b_amount": "108553.36",
        "b_entry_ids": ["ENT/2026/4088"],
    }


def test_missing_amounts_are_null(ingested, alice):
    items = {i["record_id"]: i for i in client_for(alice).get("/api/exceptions").json()}
    assert items["REC-1015"]["b_amount"] is None and items["REC-1015"]["b_entry_ids"] == []
    assert items["REC-1999"]["a_amount"] is None


# --- filters ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "query, expected",
    [
        ("?reason=TAX_NOT_RECORDED", ["REC-1027", "REC-1088"]),
        ("?location=LOC-103", ["REC-1015", "REC-1088"]),
        ("?reason=TAX_NOT_RECORDED&location=LOC-103", ["REC-1088"]),
        ("?reason=VOIDED_BUT_RECORDED", []),  # exists for ORG-B, not ORG-A
        ("?reason=&location=", ORG_A_RECORDS),  # empty means "all"
    ],
)
def test_filters(ingested, alice, query, expected):
    assert records(client_for(alice).get("/api/exceptions" + query)) == expected


def test_unknown_reason_is_400(ingested, alice):
    resp = client_for(alice).get("/api/exceptions?reason=PROFIT")
    assert resp.status_code == 400


@pytest.mark.parametrize("location", ["LOC-201", "LOC-999"])
def test_foreign_and_made_up_locations_look_the_same(ingested, alice, location):
    # Another org's location gets the same answer as one that doesn't exist.
    resp = client_for(alice).get(f"/api/exceptions?location={location}")
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Unknown location."}


# --- locations and reasons ---------------------------------------------------------

def test_locations_are_scoped(ingested, alice):
    assert client_for(alice).get("/api/locations").json() == [
        {"location_id": "LOC-101", "location_name": "Location 101"},
        {"location_id": "LOC-102", "location_name": "Location 102"},
        {"location_id": "LOC-103", "location_name": "Location 103"},
    ]


def test_locations_for_org_b(ingested, bob):
    assert [l["location_id"] for l in client_for(bob).get("/api/locations").json()] == ["LOC-201", "LOC-202"]


def test_reasons_have_plain_english_labels(alice):
    reasons = client_for(alice).get("/api/reasons").json()
    assert [r["code"] for r in reasons] == list(ReasonCode.values)
    assert len(reasons) == 8
    assert all(r["label"] and r["label"] != r["code"] for r in reasons)
