"""Risk level, primary reason code and queue priority for human handoff.

The table is the one from ``docs/05-tool-contract.md`` §7.3. Two rules matter for safety:

* ``risk_level`` is the maximum of the caller's server-side risk context and the minimum
  level of every matched code — a model-supplied value can never lower it;
* an unknown reason code is a validation error, not a new risk category.

``priority`` is fixed by level: ``critical=1``, ``high=2``, ``medium=3``, ``low=4``.
"""

from __future__ import annotations

from dataclasses import dataclass

from shopmate_ecommerce_assistant.safety.risk import RULE_ORDER, RiskLevel

_SEVERITY: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}

#: Minimum level per canonical risk rule code.
RISK_MINIMUM_LEVEL: dict[str, RiskLevel] = {
    "USER_REQUESTS_HUMAN": RiskLevel.HIGH,
    "COMPLAINT": RiskLevel.HIGH,
    "LEGAL_OR_REGULATORY": RiskLevel.CRITICAL,
    "PERSONAL_SAFETY": RiskLevel.CRITICAL,
    "PRIVACY_OR_ACCOUNT_TAKEOVER": RiskLevel.CRITICAL,
    "MONEY_DECISION_REQUIRED": RiskLevel.HIGH,
    "HIGH_VALUE_ORDER": RiskLevel.HIGH,
    "RETURN_REASON_REQUIRES_REVIEW": RiskLevel.HIGH,
    "POLICY_CONFLICT": RiskLevel.HIGH,
    "INSUFFICIENT_EVIDENCE_RIGHTS": RiskLevel.HIGH,
    "TOOL_FAILURE_REPEATED": RiskLevel.HIGH,
    "TOOL_MODEL_CONFLICT": RiskLevel.HIGH,
    "OUTPUT_GUARD_MONEY": RiskLevel.HIGH,
    "OUTPUT_GUARD_PII": RiskLevel.HIGH,
    "ABNORMAL_ORDER_PATTERN": RiskLevel.MEDIUM,
    "LOW_CONFIDENCE": RiskLevel.MEDIUM,
}

PRIORITY_BY_LEVEL: dict[RiskLevel, int] = {
    RiskLevel.CRITICAL: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.MEDIUM: 3,
    RiskLevel.LOW: 4,
}

QUEUE_BY_LEVEL: dict[RiskLevel, str] = {
    RiskLevel.CRITICAL: "priority_support",
    RiskLevel.HIGH: "priority_support",
    RiskLevel.MEDIUM: "standard_support",
    RiskLevel.LOW: "standard_support",
}


@dataclass(frozen=True, slots=True)
class ResolvedRisk:
    """The final, non-downgradable risk decision written to ``handoff_tickets``."""

    level: RiskLevel
    primary_reason_code: str
    reason_codes: tuple[str, ...]
    priority: int
    queue: str


def is_canonical_reason_code(code: str) -> bool:
    """Return True when ``code`` is a documented risk rule code."""
    return code in RISK_MINIMUM_LEVEL and code in RULE_ORDER


def resolve_risk(
    reason_code: str,
    *,
    context_level: RiskLevel = RiskLevel.LOW,
    context_codes: tuple[str, ...] = (),
) -> ResolvedRisk:
    """Combine the caller's reason with the server risk context.

    Raises:
        ValueError: when ``reason_code`` is not a canonical risk rule code.
    """
    if not is_canonical_reason_code(reason_code):
        raise ValueError("unknown risk reason code")

    known = [code for code in context_codes if is_canonical_reason_code(code)]
    codes = tuple(dict.fromkeys([reason_code, *known]))
    levels = {code: RISK_MINIMUM_LEVEL[code] for code in codes}

    level = max(
        [context_level, *levels.values()],
        key=lambda item: _SEVERITY[item],
    )
    # A context level above every code's minimum still has to be attributable to a code,
    # otherwise the ticket would carry a level with no reason. Bind it to the caller's
    # reason, which is the highest-priority signal by construction.
    if not any(levels[code] is level for code in codes):
        levels[reason_code] = level

    primary = next(
        (code for code in RULE_ORDER if code in levels and levels[code] is level),
        reason_code,
    )
    ordered = tuple(code for code in RULE_ORDER if code in levels)
    return ResolvedRisk(
        level=level,
        primary_reason_code=primary,
        reason_codes=ordered,
        priority=PRIORITY_BY_LEVEL[level],
        queue=QUEUE_BY_LEVEL[level],
    )


__all__ = [
    "PRIORITY_BY_LEVEL",
    "QUEUE_BY_LEVEL",
    "RISK_MINIMUM_LEVEL",
    "ResolvedRisk",
    "is_canonical_reason_code",
    "resolve_risk",
]
