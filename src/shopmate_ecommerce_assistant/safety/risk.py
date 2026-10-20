"""Deterministic risk classification and handoff rules.

The rule table mirrors ``docs/05-tool-contract.md`` §7.3 exactly: the same codes, the same
minimum levels and the same precedence for choosing ``primary_reason_code``. Keeping the
table in code (instead of a model prompt) is what makes "high risk must escalate"
testable.

Severity is monotonic: ``risk_level`` is the maximum over every matched rule, and the
primary code is the earliest rule *at that level* in contract order. A model can never
lower either value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

HIGH_VALUE_ORDER_CENTS = 500_000


class RiskLevel(StrEnum):
    """Risk levels, ordered by severity (see ``_SEVERITY``)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_SEVERITY: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


@dataclass(frozen=True, slots=True)
class RiskRule:
    """One contract rule: a stable code, a minimum level and text patterns."""

    code: str
    level: RiskLevel
    patterns: tuple[re.Pattern[str], ...]

    def matches(self, text: str) -> bool:
        """Return True when any pattern matches."""
        return any(pattern.search(text) for pattern in self.patterns)


def _p(*sources: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(source) for source in sources)


#: Contract order matters: it decides the primary reason code among equal levels.
RISK_RULES: tuple[RiskRule, ...] = (
    RiskRule(
        "USER_REQUESTS_HUMAN",
        RiskLevel.HIGH,
        _p(
            r"(?:转|找|要|安排|接入|联系|叫)\s*(?:一下)?\s*"
            r"(?:人工|真人|人工客服|真人客服|客服主管|主管|经理)",
            r"人工(?:客服)?(?:接管|介入|处理|跟进)",
            r"客服(?:接管|介入)",
            r"(?:不要|别)(?:机器人|ai|智能助手)",
            r"\b(?:human agent|real person|talk to (?:a )?human)\b",
        ),
    ),
    RiskRule(
        "COMPLAINT",
        RiskLevel.HIGH,
        _p(
            r"投诉|举报|维权|追责|差评|骗人|欺骗消费者|太失望|曝光你们",
            r"\bcomplaint\b",
        ),
    ),
    RiskRule(
        "LEGAL_OR_REGULATORY",
        RiskLevel.CRITICAL,
        _p(
            r"起诉|法院|律师|12315|市场监管|消协|消费者协会|法律途径|打官司|诉讼",
            r"\b(?:lawsuit|sue you|legal action)\b",
        ),
    ),
    RiskRule(
        "PERSONAL_SAFETY",
        RiskLevel.CRITICAL,
        _p(r"人身安全|威胁|恐吓|自杀|受伤|起火|爆炸|漏电|触电|误食|孩子误吞"),
    ),
    RiskRule(
        "PRIVACY_OR_ACCOUNT_TAKEOVER",
        RiskLevel.CRITICAL,
        _p(
            r"账号被盗|被盗号|盗号|隐私泄露|信息泄露|别人登录|身份被盗|盗刷|诈骗|欺诈行为",
        ),
    ),
    RiskRule(
        "MONEY_DECISION_REQUIRED",
        RiskLevel.HIGH,
        _p(
            r"(?:立刻|马上|立即|现在|直接|赶紧|尽快)\s*(?:给我|为我|帮我)?\s*"
            r"(?:退款|退钱|退货退款)",
            r"(?:给|帮|为)我\s*(?:退款|退钱|赔偿|赔钱|补偿)",
            r"(?:要求|必须|马上)\s*(?:全额)?\s*(?:退款|退钱|赔偿|赔钱)",
            r"赔我|赔偿我|退一赔三|假一赔十|免单|白送",
            r"(?:发|送|给)\s*(?:我|一张|一个)?\s*(?:优惠券|代金券|红包)",
            r"改价|改价格|修改价格|便宜点|打个折|少收点",
            r"(?:全额|双倍|三倍)\s*(?:退款|赔偿)",
        ),
    ),
)

_SIGNAL_CODES: dict[str, tuple[str, RiskLevel]] = {
    "high_value_order": ("HIGH_VALUE_ORDER", RiskLevel.HIGH),
    "return_reason_requires_review": ("RETURN_REASON_REQUIRES_REVIEW", RiskLevel.HIGH),
    "policy_conflict": ("POLICY_CONFLICT", RiskLevel.HIGH),
    "insufficient_evidence_rights": ("INSUFFICIENT_EVIDENCE_RIGHTS", RiskLevel.HIGH),
    "tool_failure_repeated": ("TOOL_FAILURE_REPEATED", RiskLevel.HIGH),
    "tool_model_conflict": ("TOOL_MODEL_CONFLICT", RiskLevel.HIGH),
    "output_guard_money": ("OUTPUT_GUARD_MONEY", RiskLevel.HIGH),
    "output_guard_pii": ("OUTPUT_GUARD_PII", RiskLevel.HIGH),
    "abnormal_order_pattern": ("ABNORMAL_ORDER_PATTERN", RiskLevel.MEDIUM),
}

#: Full contract order, used to pick ``primary_reason_code``.
RULE_ORDER: tuple[str, ...] = (
    "USER_REQUESTS_HUMAN",
    "COMPLAINT",
    "LEGAL_OR_REGULATORY",
    "PERSONAL_SAFETY",
    "PRIVACY_OR_ACCOUNT_TAKEOVER",
    "MONEY_DECISION_REQUIRED",
    "HIGH_VALUE_ORDER",
    "RETURN_REASON_REQUIRES_REVIEW",
    "POLICY_CONFLICT",
    "INSUFFICIENT_EVIDENCE_RIGHTS",
    "TOOL_FAILURE_REPEATED",
    "TOOL_MODEL_CONFLICT",
    "OUTPUT_GUARD_MONEY",
    "OUTPUT_GUARD_PII",
    "ABNORMAL_ORDER_PATTERN",
    "LOW_CONFIDENCE",
)

#: Intents where a wrong answer can cost the user money, an order or a statutory right.
RIGHTS_INTENTS = frozenset(
    {
        "policy_faq",
        "order_status",
        "shipment",
        "return_eligibility",
        "return_request",
        "complaint_handoff",
    }
)


@dataclass(frozen=True, slots=True)
class RiskSignals:
    """Non-textual evidence computed upstream (tools, retrieval, guards)."""

    amount_cents: int | None = None
    intent: str | None = None
    confidence: float | None = None
    rights_affected: bool = False
    return_reason_requires_review: bool = False
    policy_conflict: bool = False
    insufficient_evidence_rights: bool = False
    tool_failure_repeated: bool = False
    tool_model_conflict: bool = False
    output_guard_money: bool = False
    output_guard_pii: bool = False
    abnormal_order_pattern: bool = False


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """The outcome of risk classification for one turn."""

    level: RiskLevel = RiskLevel.LOW
    codes: tuple[str, ...] = ()
    primary_reason_code: str | None = None
    handoff_required: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        """Return an audit/SSE-safe representation."""
        return {
            "risk_level": self.level.value,
            "risk_codes": list(self.codes),
            "primary_reason_code": self.primary_reason_code,
            "handoff_required": self.handoff_required,
            "notes": list(self.notes),
        }


def _max_level(levels: list[RiskLevel]) -> RiskLevel:
    if not levels:
        return RiskLevel.LOW
    return max(levels, key=lambda level: _SEVERITY[level])


def _primary(codes: set[str], levels: dict[str, RiskLevel]) -> str | None:
    if not codes:
        return None
    top = _max_level([levels[code] for code in codes])
    for code in RULE_ORDER:
        if code in codes and levels[code] is top:
            return code
    return None


def assess_risk(
    text: str,
    *,
    signals: RiskSignals | None = None,
    low_confidence_threshold: float = 0.70,
) -> RiskAssessment:
    """Classify one user turn (and known signals) against the contract rule table."""
    signals = signals or RiskSignals()
    matched: list[str] = []
    levels: dict[str, RiskLevel] = {}
    for rule in RISK_RULES:
        if text and rule.matches(text):
            matched.append(rule.code)
            levels[rule.code] = _max_level([levels.get(rule.code, RiskLevel.LOW), rule.level])

    for attribute, (code, level) in _SIGNAL_CODES.items():
        if attribute == "high_value_order":
            enabled = (
                signals.amount_cents is not None and signals.amount_cents >= HIGH_VALUE_ORDER_CENTS
            )
        else:
            enabled = bool(getattr(signals, attribute))
        if enabled:
            matched.append(code)
            levels[code] = _max_level([levels.get(code, RiskLevel.LOW), level])

    notes: list[str] = []
    if signals.confidence is not None and signals.confidence < low_confidence_threshold:
        rights_affected = signals.rights_affected or (signals.intent in RIGHTS_INTENTS)
        level = RiskLevel.HIGH if rights_affected else RiskLevel.MEDIUM
        matched.append("LOW_CONFIDENCE")
        levels["LOW_CONFIDENCE"] = level
        notes.append("low_confidence_rights" if rights_affected else "low_confidence")

    unique = tuple(dict.fromkeys(matched))
    overall = _max_level([levels[code] for code in unique])
    primary = _primary(set(unique), levels)
    return RiskAssessment(
        level=overall,
        codes=unique,
        primary_reason_code=primary,
        handoff_required=_SEVERITY[overall] >= _SEVERITY[RiskLevel.HIGH],
        notes=tuple(notes),
    )


__all__ = [
    "HIGH_VALUE_ORDER_CENTS",
    "RIGHTS_INTENTS",
    "RISK_RULES",
    "RULE_ORDER",
    "RiskAssessment",
    "RiskLevel",
    "RiskRule",
    "RiskSignals",
    "assess_risk",
]
