from typing import Any


class GuideError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status = status
        self.body: dict[str, Any] = {
            "code": code,
            "message": message,
            "retryable": retryable,
        }
        if details:
            self.body["details"] = details


def not_found() -> GuideError:
    return GuideError(404, "not_found", "This item could not be found.")
