"""PII detection: address coverage plus the masking properties other guards rely on."""

from __future__ import annotations

import pytest

from shopmate_ecommerce_assistant.safety.pii import (
    PiiKind,
    contains_pii,
    find_pii,
    mask_pii,
    pii_kinds,
)

# -- address ---------------------------------------------------------------

ADDRESS_CASES = (
    # space before the house number
    "上海市浦东新区张江路 100 号",
    # no province/city prefix
    "浦东新区张江路100号",
    # space before the house number plus a trailing building name
    "北京市朝阳区建国路 88 号 SOHO 现代城",
    # unit and room must be masked together with the street address
    "上海市浦东新区张江路100号3栋501室",
)


@pytest.mark.parametrize("text", ADDRESS_CASES)
def test_shipping_address_is_detected_and_masked(text: str) -> None:
    masked, findings = mask_pii(text)
    assert [finding.kind for finding in findings] == [PiiKind.ADDRESS]
    assert pii_kinds(findings) == ("address",)
    assert "[地址已脱敏]" in masked
    # no house number, unit or room may survive the mask
    for raw in ("100", "88 号", "88号", "3栋", "501室"):
        assert raw not in masked
    assert "<" not in masked


def test_address_mask_does_not_leave_the_room_visible() -> None:
    masked, _ = mask_pii("上海市浦东新区张江路100号3栋501室")
    assert masked == "[地址已脱敏]"


def test_masking_is_idempotent_for_addresses() -> None:
    masked, findings = mask_pii(ADDRESS_CASES[0])
    assert findings
    assert find_pii(masked) == []


# -- regression: the four original kinds -----------------------------------


@pytest.mark.parametrize(
    ("text", "kind", "masked"),
    [
        ("我的手机号 13812345678", PiiKind.PHONE, "138****5678"),
        ("身份证 110101199003074518", PiiKind.ID_CARD, "1101**********4518"),
        ("银行卡 6222 0202 1234 5678", PiiKind.BANK_CARD, "**** **** **** 5678"),
        ("邮箱 zhangsan@example.com", PiiKind.EMAIL, "z***@example.com"),
    ],
)
def test_other_pii_masks_are_unchanged(text: str, kind: PiiKind, masked: str) -> None:
    result, findings = mask_pii(text)
    assert [finding.kind for finding in findings] == [kind]
    assert masked in result


def test_landline_is_still_masked() -> None:
    masked, findings = mask_pii("座机 010-12345678")
    assert pii_kinds(findings) == ("phone",)
    assert "12345678" not in masked


# -- must NOT be treated as PII -------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "订单 DEMO-1001",
        "订单号 DEMO-1001 退款多久到账",
        "SKU DEMO-HEAD-001-BLK 保修多久",
        "金额 299 元",
        "自签收之日起七日内可申请无理由退货",
        "退货运费由谁承担？",
        "七天无理由退货从什么时候开始计算？",
        "我的订单状态是什么",
    ],
)
def test_order_numbers_skus_amounts_and_policy_text_are_not_pii(text: str) -> None:
    assert find_pii(text) == []
    assert contains_pii(text) is False


def test_mixed_text_masks_only_the_address() -> None:
    masked, findings = mask_pii("订单 DEMO-1001 寄到上海市浦东新区张江路 100 号")
    assert pii_kinds(findings) == ("address",)
    assert "DEMO-1001" in masked
    assert "张江路" not in masked


def test_findings_never_store_the_raw_value() -> None:
    _, findings = mask_pii("上海市浦东新区张江路100号3栋501室")
    for finding in findings:
        assert "100" not in finding.masked
        assert "501" not in finding.masked
