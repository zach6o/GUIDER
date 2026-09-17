from uuid import uuid4

from tests.test_flow import PREFIX
from tests.test_planning import confirm, planned


async def edit_body(harness, session, plan):
    stored = (await harness.client.get(PREFIX + f"/plans/{plan.id}")).json()["data"]
    return {
        "expected_version": session["state_version"], "plan_version": plan.version,
        "steps": [{name: step[name] for name in (
            "id", "title", "action", "expected_result", "success_criterion"
        )} for step in reversed(stored["steps"])],
    }


async def test_edit_reorders_new_version_and_invalidates_old_confirmation(harness):
    _, session, plan = await planned(harness)
    confirmed = (await confirm(harness, session, plan)).json()["data"]
    body = await edit_body(harness, confirmed["session"], plan)
    body["steps"][0]["title"] = "Read the terminal output"
    path = PREFIX + f"/plans/{plan.id}/revisions"
    key = {"Idempotency-Key": str(uuid4())}
    response = await harness.client.post(path, json=body, headers=key)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["plan"]["version"] == 2
    assert data["plan"]["status"] == "draft"
    assert data["plan"]["steps"][0]["title"] == "Read the terminal output"
    assert data["session"]["confirmed_plan_version"] is None
    assert (await harness.client.post(path, json=body, headers=key)).json()["data"] == data
    assert (await confirm(harness, data["session"], plan)).status_code == 409
    latest = await harness.client.get(PREFIX + f"/sessions/{session['id']}/plan")
    assert latest.json()["data"]["id"] == data["plan"]["id"]


async def test_edits_are_checked_by_policy(harness):
    _, session, plan = await planned(harness)
    body = await edit_body(harness, session, plan)
    body["steps"][0]["action"] = "Enter your password into the payment form."
    response = await harness.client.post(PREFIX + f"/plans/{plan.id}/revisions",
        json=body, headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["plan"]["steps"][0]["policy_disposition"] == "block"


async def test_duplicate_or_foreign_step_is_rejected(harness):
    _, session, plan = await planned(harness)
    body = await edit_body(harness, session, plan)
    body["steps"][0]["id"] = body["steps"][1]["id"]
    response = await harness.client.post(PREFIX + f"/plans/{plan.id}/revisions",
        json=body, headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 422
