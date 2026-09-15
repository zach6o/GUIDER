"""The headers every response carries, whatever the response is.

An API that answers with JSON and with private image bytes has no page to
render, so the policy that fits it is the one that permits nothing. These hold
that the headers are on the ordinary path *and* on the error path, because a
failure is exactly when a response is most likely to be looked at in a browser.
"""

from uuid import uuid4

PREFIX = "/api/v1/guide"

EXPECTED = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def assert_headers(response):
    for name, value in EXPECTED.items():
        assert response.headers[name] == value
    policy = response.headers["Content-Security-Policy"]
    assert "default-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy


async def test_a_successful_response_carries_the_policy(harness):
    response = await harness.client.post(
        PREFIX + "/tasks",
        json={"goal": "Why won't Python run?", "category": "debug",
              "application_key": "powershell"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201
    assert_headers(response)


async def test_an_error_carries_it_too(harness):
    # The one people actually open in a browser tab.
    response = await harness.client.get(PREFIX + f"/tasks/{uuid4()}")
    assert response.status_code == 404
    assert_headers(response)


async def test_an_unauthenticated_response_carries_it(harness):
    response = await harness.client.get(PREFIX + "/tasks", headers={"Authorization": "Bearer no"})
    assert response.status_code in (401, 404, 405)
    assert_headers(response)
