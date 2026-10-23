"""SSE streaming chat endpoint (docs/06-api.md sections 6.2 and 7)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from shopmate_ecommerce_assistant.agents.chat_service import ChatService
from shopmate_ecommerce_assistant.agents.sse import SSESerializer, error_event
from shopmate_ecommerce_assistant.api.deps import (
    get_access_context,
    get_rate_limiter,
    get_request_ids,
    get_settings_dep,
)
from shopmate_ecommerce_assistant.api.schemas import ChatStreamRequest
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.generation import GenerationParams
from shopmate_ecommerce_assistant.core.rate_limit import RateLimiter
from shopmate_ecommerce_assistant.core.security import AccessContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _resolve_policy(policy_factory, static_policy, session):
    """Return the policy service for this stream.

    ``policy_factory`` (the wired RAG path) takes precedence and binds a
    ``PolicyQAService`` to *this* request's session, because the PostgreSQL authorizer
    inside the retriever must not outlive it. A static ``policy`` (tests) is used when no
    factory is installed. Any construction failure degrades to ``None``: the chat service
    then emits its fixed "知识库暂不可用" answer rather than guessing.
    """
    if policy_factory is None:
        return static_policy
    try:
        return policy_factory(session)
    except Exception:
        logger.exception("policy service construction failed; reporting unavailable")
        return None


@router.post("/stream")
async def chat_stream(
    body: ChatStreamRequest,
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> StreamingResponse:
    allowed, retry_after = await limiter.check(
        f"chat:{context.user_id}", limit=settings.rate_limit_chat_per_minute, window_seconds=60
    )
    if not allowed:
        raise ToolError(
            ErrorCode.RATE_LIMITED,
            "消息发送过于频繁，请稍后重试。",
            retryable=True,
            retry_after_ms=int(retry_after * 1000),
        )

    request_id, trace_id = get_request_ids(request)
    factory = request.app.state.session_factory
    policy_factory = getattr(request.app.state, "policy_factory", None)
    static_policy = getattr(request.app.state, "policy", None)

    # Pre-flight (must finish before the SSE stream is established so 404/409 stay JSON).
    async with factory() as session:
        service = ChatService(session=session, settings=settings, policy=static_policy)
        # Ownership check + the conversation's stage-18 knowledge-base selection and
        # stage-19 generation-parameter overrides. An empty selection keeps the
        # pre-existing "no restriction" retrieval scope; missing overrides keep the
        # environment LLM defaults, so old conversations behave exactly as before.
        conversation = await service.ensure_conversation(context, body.conversation_id)
        knowledge_base_ids = conversation.knowledge_base_ids
        generation = GenerationParams.resolve(conversation.generation_params, settings=settings)
        user_message_id = await service.insert_user_message(
            context, body.conversation_id, body.message, body.client_message_id
        )

    async def event_stream():
        serializer = SSESerializer(request_id)
        async with factory() as session:
            policy = _resolve_policy(policy_factory, static_policy, session)
            service = ChatService(session=session, settings=settings, policy=policy)
            try:
                async for event in service.stream(
                    ctx=context,
                    conversation_id=body.conversation_id,
                    message=body.message,
                    request_id=request_id,
                    trace_id=trace_id,
                    user_message_id=user_message_id,
                    knowledge_base_ids=knowledge_base_ids,
                    generation=generation,
                ):
                    yield serializer.frame(event)
            except Exception:
                # The service already maps expected errors to a terminal ``error`` event;
                # this is the fail-closed path for anything it did not anticipate.
                logger.exception("chat stream failed unexpectedly")
                yield serializer.frame(
                    error_event(
                        {
                            "error_code": ErrorCode.INTERNAL_ERROR.value,
                            "user_message": "服务暂时不可用，请稍后重试。",
                            "retryable": True,
                            "retry_after_ms": None,
                            "partial_message_id": None,
                            "partial_persisted": False,
                        }
                    )
                )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


__all__ = ["router"]
