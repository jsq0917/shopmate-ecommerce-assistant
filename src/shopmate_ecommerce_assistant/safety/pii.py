"""PII detection and masking.

The MVP only handles synthetic data, but user text can still contain a phone number,
an ID card, a bank card, an e-mail or a shipping address. Those values must not reach
logs, caches or the model context verbatim, so this module finds them deterministically
and returns only *masked* representations plus character spans.

Design choices:

* No raw value is stored in :class:`PiiFinding`. A finding is safe to log.
* Overlapping matches are resolved longest-first, so an 18-digit ID card is not also
  reported as a bank card.
* Masking is idempotent: an already-masked value (``138****1234``) is not matched again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class PiiKind(StrEnum):
    """Kinds of personal data the guards recognise."""

    PHONE = "phone"
    ID_CARD = "id_card"
    BANK_CARD = "bank_card"
    EMAIL = "email"
    ADDRESS = "address"


@dataclass(frozen=True, slots=True)
class PiiFinding:
    """One masked PII occurrence. ``value`` is never the original text."""

    kind: PiiKind
    masked: str
    start: int
    end: int


#: House number plus the unit/room suffix that belongs to the same address. A shipping
#: address is not "safe" while ``3栋501室`` is still visible, so the mask has to reach the
#: room, not stop at 号.
_HOUSE_NUMBER = r"\s*\d+\s*号(?:\s*\d+\s*(?:栋|幢|单元|号楼|楼|层|室|户)){0,3}"

#: Everything after the district keyword: an optional estate name, the road keyword, an
#: optional lane/compound token, and finally the house number.
_STREET_TAIL = (
    r"[\u4e00-\u9fff0-9]{0,20}"
    r"(?:路|街|巷|道|大街|大道)"
    r"[\u4e00-\u9fff0-9]{0,12}" + _HOUSE_NUMBER
)

# Ordered by specificity: ID card and bank card are checked before the phone pattern
# because an 11-digit phone is a substring of neither, but a bank card contains digits
# that could otherwise be split into several "phones".
_PATTERNS: tuple[tuple[PiiKind, re.Pattern[str]], ...] = (
    (
        PiiKind.EMAIL,
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"),
    ),
    (
        PiiKind.ID_CARD,
        re.compile(
            r"(?<![0-9A-Za-z])[1-9]\d{5}(?:19|20)\d{2}"
            r"(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?![0-9A-Za-z])"
        ),
    ),
    (
        PiiKind.BANK_CARD,
        re.compile(r"(?<!\d)(?:\d{4}[ -]?){3}\d{4,7}(?!\d)"),
    ),
    (
        PiiKind.PHONE,
        re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    ),
    (
        PiiKind.PHONE,
        re.compile(r"(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)"),
    ),
    (
        # Full form: province/city + district + road + house number (+ unit/room).
        PiiKind.ADDRESS,
        re.compile(
            r"[\u4e00-\u9fff]{2,8}(?:省|自治区|市)[\u4e00-\u9fff]{0,10}"
            r"(?:区|县|镇|乡|街道)" + _STREET_TAIL
        ),
    ),
    (
        # Short form: users often omit the province/city ("浦东新区张江路100号").
        # The district keyword is mandatory, so a bare "100号" or an order number
        # such as DEMO-1001 can never be mistaken for an address.
        PiiKind.ADDRESS,
        re.compile(r"(?:区|县|镇|乡|街道)" + _STREET_TAIL),
    ),
)


def _mask(kind: PiiKind, value: str) -> str:
    if kind is PiiKind.EMAIL:
        local, _, domain = value.partition("@")
        head = local[:1] or "*"
        return f"{head}***@{domain}"
    if kind is PiiKind.PHONE:
        digits = re.sub(r"\D", "", value)
        if len(digits) == 11:
            return f"{digits[:3]}****{digits[-4:]}"
        return f"{digits[:3]}****{digits[-3:]}" if len(digits) > 6 else "***"
    if kind is PiiKind.ID_CARD:
        return f"{value[:4]}{'*' * 10}{value[-4:]}"
    if kind is PiiKind.BANK_CARD:
        digits = re.sub(r"\D", "", value)
        return f"**** **** **** {digits[-4:]}"
    return "[地址已脱敏]"


def find_pii(text: str) -> list[PiiFinding]:
    """Return non-overlapping PII findings ordered by position."""
    if not text:
        return []
    candidates: list[PiiFinding] = []
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            candidates.append(
                PiiFinding(
                    kind=kind,
                    masked=_mask(kind, match.group(0)),
                    start=match.start(),
                    end=match.end(),
                )
            )
    # Longest match wins; ties keep the earlier (more specific) pattern.
    candidates.sort(key=lambda item: (-(item.end - item.start), item.start))
    accepted: list[PiiFinding] = []
    for finding in candidates:
        if any(finding.start < other.end and other.start < finding.end for other in accepted):
            continue
        accepted.append(finding)
    accepted.sort(key=lambda item: item.start)
    return accepted


def contains_pii(text: str) -> bool:
    """Return True when any recognised PII appears in ``text``."""
    return bool(find_pii(text))


def mask_pii(text: str) -> tuple[str, list[PiiFinding]]:
    """Return ``(masked_text, findings)``; findings never contain the raw value."""
    findings = find_pii(text)
    if not findings:
        return text, []
    pieces: list[str] = []
    cursor = 0
    for finding in findings:
        pieces.append(text[cursor : finding.start])
        pieces.append(finding.masked)
        cursor = finding.end
    pieces.append(text[cursor:])
    return "".join(pieces), findings


def pii_kinds(findings: list[PiiFinding]) -> tuple[str, ...]:
    """Return the sorted, de-duplicated kinds for audit records."""
    return tuple(sorted({finding.kind.value for finding in findings}))


__all__ = [
    "PiiFinding",
    "PiiKind",
    "contains_pii",
    "find_pii",
    "mask_pii",
    "pii_kinds",
]
