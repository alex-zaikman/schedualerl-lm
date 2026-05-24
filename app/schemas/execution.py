from pydantic import BaseModel, ConfigDict, Field

from app.enums import ExecutionSource


class WebhookFireOutcome(BaseModel):
    """HTTP outcome from firing a webhook (no routing context)."""

    model_config = ConfigDict(frozen=True)

    http_status: int | None = Field(
        default=None,
        description="HTTP status code from the webhook, when a response was received.",
    )
    error_message: str | None = Field(
        default=None,
        description="Error detail when the webhook call failed.",
    )
    success: bool = Field(description="Whether the webhook returned a 2xx status.")


class WebhookFireResult(WebhookFireOutcome):
    """Full execution outcome exposed in API responses and history."""

    execution_source: ExecutionSource = Field(
        description="Whether the fire was scheduled or manual.",
    )
    webhook_url: str = Field(description="Webhook URL that was called.")


def webhook_fire_result(
    *,
    execution_source: ExecutionSource,
    webhook_url: str,
    outcome: WebhookFireOutcome,
) -> WebhookFireResult:
    return WebhookFireResult(
        execution_source=execution_source,
        webhook_url=webhook_url,
        http_status=outcome.http_status,
        error_message=outcome.error_message,
        success=outcome.success,
    )
