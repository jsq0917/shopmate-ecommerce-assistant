"""Deterministic safety guards for the ShopMate chat path.

Nothing in this package calls a model: input/output checks are rule-based so a prompt
injection cannot talk its way past them. The guards return structured findings instead of
raising, because the caller has to decide between answering, redacting, refusing and
handing off to a human.
"""

from shopmate_ecommerce_assistant.safety.input_guard import (
    InputGuardResult,
    guard_input,
)
from shopmate_ecommerce_assistant.safety.output_guard import (
    OutputGuardResult,
    guard_output,
)
from shopmate_ecommerce_assistant.safety.risk import (
    RiskAssessment,
    RiskLevel,
    RiskSignals,
    assess_risk,
)

__all__ = [
    "InputGuardResult",
    "OutputGuardResult",
    "RiskAssessment",
    "RiskLevel",
    "RiskSignals",
    "assess_risk",
    "guard_input",
    "guard_output",
]
