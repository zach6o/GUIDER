"""OpenAI adapter for the `guide` role. Moved from `app.cloud` unchanged.

Contacts only `https://api.openai.com/v1` with TLS, no redirects and no ambient
environment credentials, per ADR-015. The credential arrives per call and is
never held here.
"""

import base64
import json

import httpx
from pydantic import SecretStr, ValidationError

from app.errors import GuideError
from app.guide.guard import POLICY
from app.providers.base import CheckInput, Guidance, provider_error
from app.providers.schema import personal_schema, render

# What a bring-your-own-key connection may ask for, cheapest-capable first.
MODELS: tuple[str, ...] = ("gpt-4.1-mini", "gpt-4.1")


class OpenAIVision:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    def client(self, api_key: SecretStr) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url="https://api.openai.com/v1/",
            headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
            timeout=httpx.Timeout(45, connect=10),
            follow_redirects=False,
            trust_env=False,
            transport=self.transport,
        )

    async def validate(self, key: SecretStr, model: str) -> None:
        try:
            async with self.client(key) as client:
                response = await client.get(f"models/{model}")
            if response.status_code != 200:
                raise provider_error(response.status_code)
        except httpx.HTTPError:
            raise GuideError(
                503, "openai_unavailable", "Could not connect to OpenAI. Check your connection."
            ) from None

    async def personal(self, key, model, context, schema, image=None):
        from app.personal_types import POLICY as PERSONAL_POLICY

        content = [{"type": "input_text", "text": json.dumps(context)}]
        if image is not None:
            content.append(
                {
                    "type": "input_image",
                    "detail": "high",
                    "image_url": "data:image/png;base64," + base64.b64encode(image).decode(),
                }
            )
        return await self.structured(
            key,
            {
                "model": model,
                "store": False,
                "max_output_tokens": 5000,
                "instructions": PERSONAL_POLICY,
                "input": [{"role": "user", "content": content}],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "personal_guide",
                        "strict": True,
                        "schema": personal_schema(schema),
                    }
                },
            },
            schema,
        )

    async def analyze(self, key: SecretStr, model: str, body: CheckInput, image: bytes) -> Guidance:
        payload = {
            "model": model,
            "store": False,
            "max_output_tokens": 1100,
            "instructions": POLICY,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "goal": body.goal,
                                    "question": body.question,
                                    "previous_step_unverified": body.previous_step,
                                }
                            ),
                        },
                        {
                            "type": "input_image",
                            "detail": "high",
                            "image_url": "data:image/png;base64,"
                            + base64.b64encode(image).decode(),
                        },
                    ],
                }
            ],
            "text": render(Guidance, "guider_step", "json_schema"),
        }
        return await self.structured(key, payload, Guidance)

    async def structured(self, key, payload, schema):
        try:
            async with self.client(key) as client:
                response = await client.post("responses", json=payload)
            if response.status_code != 200:
                raise provider_error(response.status_code)
            result = response.json()
            if result.get("status") != "completed":
                raise GuideError(
                    503, "incomplete_answer", "The answer was incomplete. Please check again."
                )
            texts = [
                part["text"]
                for item in result.get("output", [])
                if item.get("type") == "message"
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            ]
            if len(texts) != 1:
                raise ValueError("No complete structured answer")
            # A proposal only. app.guide.guard vets it at the call site; this
            # adapter deliberately cannot approve its own output.
            return schema.model_validate_json(texts[0])
        except httpx.HTTPError:
            raise GuideError(
                503, "openai_unavailable", "The connection to OpenAI was interrupted. Try again."
            ) from None
        except (ValueError, KeyError, TypeError, ValidationError):
            raise GuideError(
                503, "invalid_answer", "Guider could not validate that answer. Try a clearer view."
            ) from None
