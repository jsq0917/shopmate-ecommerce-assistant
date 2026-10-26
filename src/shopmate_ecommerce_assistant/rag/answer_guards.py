"""Deterministic answer guards shared by the policy service and the output guard.

These functions live in their own module so ``safety.output_guard`` and
``rag.policy_qa`` can share one implementation without importing each other —
the previous ``policy_qa -> retrieval -> repositories -> models -> safety ->
output_guard -> policy_qa`` cycle made a bare ``import rag.policy_qa`` fail
depending on import order, which is exactly the kind of landmine a fresh script
or deployment tool steps on.

The rules themselves are unchanged; only their home moved. ``rag.policy_qa``
re-exports every public name for backwards compatibility with existing callers
and tests.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from shopmate_ecommerce_assistant.rag.citations import Citation

_LABEL = re.compile(r"\[(c\d+)\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？；\n])")
_SENTENCE_ENDINGS = "。！？；\n"

#: The two sentinels the prompt asks the model to emit, plus everything that may legally
#: surround them: citation labels, whitespace and sentence-final punctuation.
_SENTINEL = re.compile(r"\[\s*c\d+\s*\]", re.IGNORECASE)
_SENTINEL_TRIM = " \t\r\n\u3000。．.！!？?；;：:，,、\"'“”‘’（）()【】[]"


def sentinel_of(text: str) -> str | None:
    """Return ``"NO_EVIDENCE"`` / ``"CONFLICT"`` when ``text`` *is* that sentinel.

    Stage 13 found a fail-open: the model emitted ``NO_EVIDENCE [c1][c2]…`` instead of a
    bare sentinel, so an exact-equality check missed it, the citation guard accepted the
    labels, and the sentinel string itself was shown to the user as the answer
    (``eval-058`` / ``eval-061``).

    The match therefore normalises first — strip citation labels, surrounding whitespace
    and trailing sentence punctuation, then compare case-insensitively — so any sentinel
    that reaches this point is routed to the refusal / handoff branch instead of the
    answer body. A real answer that merely *contains* the words is untouched.
    """
    core = _SENTINEL.sub("", text).strip().rstrip(_SENTINEL_TRIM).strip()
    upper = core.upper()
    if upper == "NO_EVIDENCE":
        return "NO_EVIDENCE"
    if upper == "CONFLICT":
        return "CONFLICT"
    return None


#: Only transitional / action-guidance sentences may appear without a ``[cN]`` label.
#: Everything else is treated as a policy claim, so a claim phrased without any of the
#: old keyword hints ("退货需保持商品完好。") can no longer slip through.
_TRANSITIONAL_OPENERS = (
    "如需",
    "如果需要",
    "建议",
    "你可以",
    "您可以",
    "请联系",
    "如有疑问",
    "以上",
)

#: Minimal output guard (stage 7 scope): the model must never assert that money has
#: already moved or been approved. A bare "赔付" is deliberately *not* matched — the
#: corpus itself discusses 赔付 rules, so only completed/approved phrasings are flagged.
_COMMITMENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "refund_completed",
        re.compile(r"(?:已|已经|现已)(?:完成)?(?:为你|为您|给你|给您)?退款|退款成功"),
    ),
    (
        "refund_approved",
        re.compile(
            r"退款(?:已|已经)(?:批准|通过)|"
            r"已(?:经)?(?:批准|通过)(?:了)?(?:你的|您的)?(?:退款|退货|赔付|申请)"
        ),
    ),
    (
        "compensation_decided",
        re.compile(r"已(?:经)?(?:为你|为您|给你|给您)?(?:赔付|补偿|打款)"),
    ),
    ("free_order", re.compile(r"免单")),
    (
        "coupon_issued",
        re.compile(r"(?:优惠券|代金券)(?:已|已经)发放|已(?:经)?发放(?:优惠券|代金券)"),
    ),
)
_NEGATION_BEFORE = re.compile(r"(?:不|未|没有|无法|不能|不予|不会|不得|不可)[^。！？；\n]{0,6}$")


def used_labels(text: str) -> list[str]:
    """Return citation labels referenced by the answer, preserving order."""
    seen: list[str] = []
    for label in _LABEL.findall(text):
        if label not in seen:
            seen.append(label)
    return seen


def _is_transitional(sentence: str) -> bool:
    """Return True for sentences that carry no policy claim of their own."""
    core = sentence.strip().rstrip(_SENTENCE_ENDINGS).strip()
    if not core:
        return True
    if core.endswith(("：", ":")):
        return True
    return core.startswith(_TRANSITIONAL_OPENERS)


def citation_label_issues(text: str, available_labels: Sequence[str]) -> list[str]:
    """Deterministically check that every policy claim is backed by a provided label.

    Label-based so the same rules can re-validate a *cached* answer without rebuilding
    ``Citation`` objects, and so the output guard shares one implementation with stage 7.
    """
    issues: list[str] = []
    # A sentinel carries no answer, so its labels (if any) are irrelevant: checking them
    # first would report ``unknown_citation`` on ``CONFLICT [c1][c2]`` and hide the fact
    # that the model refused. Normalise once, before anything else looks at labels.
    if sentinel_of(text) is not None:
        return issues
    available = set(available_labels)
    labels = used_labels(text)
    unknown = [label for label in labels if label not in available]
    if unknown:
        issues.append(f"unknown_citation:{','.join(unknown)}")
    if not labels:
        issues.append("missing_citation")
        return issues
    for sentence in _SENTENCE_SPLIT.split(text):
        stripped = sentence.strip()
        if not stripped or _LABEL.search(stripped):
            continue
        if _is_transitional(stripped):
            continue
        issues.append("uncited_claim")
        break
    return issues


def citation_issues(text: str, citations: list[Citation]) -> list[str]:
    """Deterministically check that every policy claim is backed by a provided citation."""
    return citation_label_issues(text, [citation.label for citation in citations])


def commitment_issues(text: str) -> list[str]:
    """Return unauthorised money-commitment findings in a model draft.

    This is the minimal output guard for stage 7. It only looks for *asserted* outcomes
    ("已退款", "退款已批准", "免单"), never for policy descriptions of a refund process.
    """
    findings: list[str] = []
    for code, pattern in _COMMITMENT_RULES:
        for match in pattern.finditer(text):
            prefix = text[max(0, match.start() - 8) : match.start()]
            if _NEGATION_BEFORE.search(prefix):
                continue
            issue = f"unauthorized_commitment:{code}"
            if issue not in findings:
                findings.append(issue)
    return findings


__all__ = [
    "citation_issues",
    "citation_label_issues",
    "commitment_issues",
    "sentinel_of",
    "used_labels",
]
