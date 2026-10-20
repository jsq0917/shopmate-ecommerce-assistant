"""Shared strict-schema validation for tools."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError

GENERIC_VALIDATION_MESSAGE = "请求参数不合法，请检查订单号、订单项、原因或幂等键是否符合要求。"


def validate_input[T: BaseModel](
    model: type[T], payload: Any, *, message: str = GENERIC_VALIDATION_MESSAGE
) -> T:
    """Validate a payload and convert schema errors into a safe :class:`ToolError`.

    The pydantic message is dropped on purpose: it quotes the offending input, which may
    contain user text.
    """
    if isinstance(payload, model):
        return payload
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ToolError(ErrorCode.VALIDATION_ERROR, message) from exc


__all__ = ["GENERIC_VALIDATION_MESSAGE", "validate_input"]
