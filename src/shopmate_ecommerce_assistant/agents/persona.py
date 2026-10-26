"""Human-sounding rewriting of deterministic answers.

The chat path composes answers from verified tool facts with fixed templates. Those
templates are honest but robotic. This module asks the configured LLM to *rephrase* the
draft — never to re-derive it — and refuses the rewrite unless it is provably faithful:

* every digit in the rewrite must already appear in the draft (no invented price, stock
  count, order number or deadline);
* forbidden commitment phrases ("保证退款", "一定可以退", "百分百") reject the rewrite;
* links/HTML reject the rewrite;
* an over-long rewrite (``max_chars``) rejects the rewrite.

On any failure, timeout or missing configuration the deterministic draft is returned
unchanged, so the chat path degrades to stage-13 behaviour instead of losing an answer.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.generation import GenerationParams
from shopmate_ecommerce_assistant.rag.policy_qa import (
    AnswerModel,
    AnswerModelError,
    build_answer_model,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是 ShopMate 电商商城的在线客服，说话自然、口语化、有温度，但绝不夸张。
你的任务只是把系统已经生成的答复改写得更像人在说话。

必须遵守：
1. 不得新增、删除或修改任何数字、金额、型号、SKU、订单号、工单号、退款单号、库存数量、时效；
2. 不得新增政策条款，不得承诺退款/赔偿/优惠，不得说"保证""一定""百分百"；
3. 不得改变结论：无货不能写成有货，不符合退货条件不能写成符合；
4. 不得输出链接、HTML、代码块、表情符号，不要称呼"亲"；
5. 用简体中文，1-3 句话，不超过 120 字，不要分点罗列；
6. 只输出改写后的答复本身，不要解释，不要加引号。"""


@dataclass(frozen=True, slots=True)
class PersonaResult:
    """The text to stream plus whether the LLM rewrite was used."""

    text: str
    rewritten: bool
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"rewritten": self.rewritten, "reason": self.reason}


_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_FORBIDDEN = re.compile(
    r"保证\s*(?:退款|退货|赔偿|到账)|一定\s*(?:能|可以|会)?\s*(?:退|赔)|百分百|100\s*%|"
    r"绝对\s*(?:能|可以|会)\s*(?:退|赔)|包退|包赔"
)
_UNSAFE = re.compile(r"https?://|<\s*\w+[^>]*>|```", re.I)


def _numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(text))


def _faithful(draft: str, candidate: str, *, max_chars: int) -> str | None:
    """Return a rejection reason, or ``None`` when the rewrite is acceptable."""
    text = candidate.strip().strip('"').strip("“”")
    if not text:
        return "empty"
    if len(text) > max_chars:
        return "too_long"
    if _FORBIDDEN.search(text):
        return "forbidden_commitment"
    if _UNSAFE.search(text):
        return "unsafe_markup"
    invented = _numbers(text) - _numbers(draft)
    if invented:
        return "invented_number"
    return None


def naturalize(
    draft: str,
    *,
    user_text: str,
    settings: Settings,
    model: AnswerModel | None = None,
    history: list[str] | None = None,
    generation: GenerationParams | None = None,
) -> PersonaResult:
    """Rewrite ``draft`` into conversational Chinese, or return it unchanged.

    The call is synchronous (the underlying client is ``httpx.Client``); callers inside the
    async chat pipeline must wrap it in ``asyncio.to_thread``. ``generation`` forwards the
    conversation's stage-19 parameter overrides to the model; ``None`` keeps the
    environment defaults.
    """
    if not settings.chat_persona_enabled:
        return PersonaResult(draft, False, "disabled")
    cleaned = draft.strip()
    # Very short fallbacks ("好的。") gain nothing from a rewrite and cost a round-trip.
    if len(cleaned) < 12:
        return PersonaResult(draft, False, "too_short")

    llm = model if model is not None else build_answer_model(settings)
    if llm is None:
        return PersonaResult(draft, False, "no_model")

    context = ""
    if history:
        recent = " / ".join(item.strip() for item in history[-2:] if item.strip())
        if recent:
            context = f"\n最近的对话（供参考，不要复述）：{recent}"
    prompt = (
        f"用户刚刚说：{user_text}{context}\n\n系统生成的答复：{cleaned}\n\n请按要求改写这段答复。"
    )
    try:
        candidate = llm.complete(system=SYSTEM_PROMPT, user=prompt, generation=generation)
    except AnswerModelError as exc:
        logger.info("chat persona rewrite skipped: %s", exc.code)
        return PersonaResult(draft, False, exc.code)
    except Exception:  # pragma: no cover - transport differences
        logger.warning("chat persona rewrite failed unexpectedly")
        return PersonaResult(draft, False, "exception")

    logger.debug("persona draft=%r candidate=%r", cleaned, candidate)
    max_chars = max(120, min(240, len(cleaned) * 2))
    rejection = _faithful(cleaned, candidate, max_chars=max_chars)
    if rejection is not None:
        logger.info("chat persona rewrite rejected: %s", rejection)
        return PersonaResult(draft, False, rejection)
    return PersonaResult(candidate.strip().strip('"').strip("“”"), True, "ok")


async def naturalize_async(
    draft: str,
    *,
    user_text: str,
    settings: Settings,
    model: AnswerModel | None = None,
    history: list[str] | None = None,
    generation: GenerationParams | None = None,
) -> PersonaResult:
    """Await :func:`naturalize` in a worker thread with a hard timeout."""
    timeout = settings.chat_persona_timeout_seconds
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                naturalize,
                draft,
                user_text=user_text,
                settings=settings,
                model=model,
                history=history,
                generation=generation,
            ),
            timeout=timeout,
        )
    except TimeoutError:
        logger.info("chat persona rewrite timed out after %.1fs", timeout)
        return PersonaResult(draft, False, "timeout")


__all__ = ["PersonaResult", "SYSTEM_PROMPT", "naturalize", "naturalize_async"]
