"""Deterministic answer composition for the chat path.

The composer turns verified tool facts into a plain-Chinese answer. It never invents a
price, stock number or status: every number it prints was produced by a tool and passed in
here. Money is always shown from ``*_cents`` as a whole-yuan amount, never a float.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from shopmate_ecommerce_assistant.agents.router import Intent


def _yuan(cents: int) -> str:
    """Render integer cents as a whole-yuan string, e.g. 29900 -> '299'."""
    if cents % 100 == 0:
        return str(cents // 100)
    return f"{cents / 100:.2f}".rstrip("0").rstrip(".")


def _stock_label(status: str, qty: int | None) -> str:
    if status == "in_stock":
        return f"有货（{qty} 件）" if qty is not None else "有货"
    if status == "out_of_stock":
        return "暂时无货"
    return "库存待确认"


def _stock_inline(status: str, qty: int | None) -> str:
    """Bare stock phrase for use *inside* another parenthetical.

    ``_stock_label`` already carries its own brackets ("有货（60 件）"), so embedding it in
    "（¥299，…）" produced a doubled "）". The inline form keeps the list readable.
    """
    if status == "in_stock":
        return f"有货 {qty} 件" if qty is not None else "有货"
    if status == "out_of_stock":
        return "暂时无货"
    return "库存待确认"


def compose_product_discovery(
    cards: list[Mapping[str, Any]], *, question: str | None = None
) -> str:
    """Return a recommendation list built only from the search cards."""
    if not cards:
        return (
            "这次没找到完全匹配的商品。换个说法（比如只写品类）或者把预算放宽一点，"
            "我再帮你找找；也可以直接去「商品中心」按分类慢慢挑。"
        )
    lines = ["按你的要求，我挑了几款比较合适的："]
    for index, card in enumerate(cards[:4], start=1):
        price = _yuan(int(card["price_cents"]))
        stock = _stock_inline(card["stock_status"], card.get("available_qty"))
        lines.append(f"{index}. {card['title']} — ¥{price}，{stock}")
    lines.append("点开卡片可以看参数和规格，需要的话我也能帮你横向对比。")
    return "\n".join(lines)


def compose_purchase_intro(cards: list[Mapping[str, Any]]) -> str:
    """Return a short buying guide plus the matching cards."""
    if not cards:
        return (
            "想下单的话，可以在「商品中心」里挑好商品，进入详情选规格后点「立即购买」，"
            "确认地址就能提交订单，付款后我这边可以帮你查订单和物流。"
        )
    lines = ["这几款都可以直接下单，流程是：打开商品 → 选规格 → 立即购买 → 确认订单 → 支付。"]
    for index, card in enumerate(cards[:3], start=1):
        price = _yuan(int(card["price_cents"]))
        stock = _stock_inline(card["stock_status"], card.get("available_qty"))
        lines.append(f"{index}. {card['title']} — ¥{price}，{stock}")
    lines.append("付款后如果还没发货，也可以在订单详情里直接取消。")
    return "\n".join(lines)


def compose_product_detail(product: Mapping[str, Any]) -> str:
    """Return a short product summary with its cheapest/available SKUs."""
    title = product["title"]
    brand = product.get("brand") or ""
    summary = product.get("stock_summary") or {}
    stock = _stock_label(summary.get("stock_status", "unknown"), summary.get("available_qty"))
    variants = product.get("variants") or []
    lines = [f"{title}" + (f"（{brand}）" if brand else ""), f"库存：{stock}"]
    for variant in variants[:3]:
        price = _yuan(int(variant["price_cents"]))
        lines.append(f"· {variant['title']} — ¥{price}")
    return "\n".join(lines)


def compose_compare(compare: Mapping[str, Any]) -> str:
    """Return a compact comparison of the aligned rows."""
    products = compare.get("products") or []
    rows = compare.get("rows") or []
    if not products:
        return "未能完成商品对比，请稍后重试。"
    headers = " | ".join(p["title"] for p in products)
    lines = [f"对比：{headers}"]
    for row in rows[:8]:
        cells = " | ".join(str(v["display"]) for v in row["values"])
        lines.append(f"{row['label']}：{cells}")
    return "\n".join(lines)


def compose_order_status(data: Mapping[str, Any]) -> str:
    """Return the order's current status and amount."""
    status_map = {
        "created": "已创建，等待付款",
        "paid": "已支付，等待发货",
        "processing": "备货中",
        "shipped": "已发货",
        "delivered": "已签收",
        "completed": "已完成",
        "cancelled": "已取消",
    }
    status = status_map.get(str(data["status"]), str(data["status"]))
    total = _yuan(int(data["total_cents"]))
    return (
        f"订单 {data['order_no']} 目前是「{status}」，金额 ¥{total}。"
        "想看物流进度或申请退款、退货，可以在「我的订单」里打开这笔订单。"
    )


def compose_shipment(data: Mapping[str, Any]) -> str:
    """Return the latest logistics status with the masked tracking number."""
    status_map = {
        "pending": "待揽收",
        "picked_up": "已揽收",
        "in_transit": "运输中",
        "out_for_delivery": "派送中",
        "delivered": "已签收",
        "exception": "异常",
    }
    status = status_map.get(str(data["status"]), str(data["status"]))
    carrier = data.get("carrier") or "承运商"
    tracking = data.get("tracking_no_masked") or "—"
    events = data.get("events") or []
    lines = [f"物流（{carrier}）当前状态：{status}，运单号 {tracking}。"]
    if events:
        latest = events[-1]
        lines.append(f"最新节点：{latest['description']}")
    return "\n".join(lines)


def compose_return_eligibility(data: Mapping[str, Any]) -> str:
    """Return the eligibility decision in plain language."""
    decision = str(data["decision"])
    if decision == "eligible":
        materials = "、".join(data.get("required_materials") or []) or "无特殊材料"
        return (
            f"这件商品可以退。需要准备：{materials}。"
            "在「我的订单」里打开这笔订单，点「申请退货」按提示提交就行，"
            "提交后可以在「我的工单」旁边看到处理进度。"
        )
    if decision == "ineligible":
        code = str(data.get("decision_code") or "")
        reasons = {
            "RETURN_WINDOW_EXPIRED": (
                "已经超过签收后 7 天的退货窗口，这种情况只能走保修或转人工协商。"
            ),
            "DUPLICATE_RETURN": "这件商品已经有进行中的退货申请了，不用重复提交。",
            "RETURN_NOT_ALLOWED": "这件商品不在自助退货范围内（比如食品、已拆封的个人护理用品）。",
            "INVALID_STATE": "当前订单状态不支持退货，可能还没签收或已经取消。",
            "ORDER_NOT_FOUND": "没找到可退货的订单或商品，麻烦核对一下订单号。",
        }
        return reasons.get(code, "这件商品暂时不符合自助退货条件。")
    if decision == "needs_clarification":
        return "还得确认一下具体原因：是尺码不合适、不想要了，还是商品有破损或质量问题？"
    return "这笔退货需要人工核实一下，我建议直接转人工，让客服帮你看具体情况。"


SMALLTALK_REPLIES: dict[Intent, str] = {
    Intent.SMALLTALK_OR_UNKNOWN: (
        "你好呀，我是 ShopMate 的导购助手。找商品、查订单物流、问退换货政策都可以交给我，"
        "你想先看点什么？"
    ),
}

_GREETING = re.compile(r"你好|您好|在吗|嗨|hello|hi\b", re.I)
_THANKS = re.compile(r"谢谢|感谢|辛苦", re.I)
_BYE = re.compile(r"再见|拜拜|下次聊", re.I)
_IDENTITY = re.compile(r"你是谁|你能做什么|会什么|怎么使用你")
_OFFTOPIC = re.compile(r"天气|笑话|唱歌|股票|写诗")


def compose_smalltalk(
    intent: Intent, clarification_text: str | None, *, text: str | None = None
) -> str:
    """Return a safe, on-topic reply for smalltalk or a clarifying question."""
    if clarification_text:
        return clarification_text
    said = text or ""
    if _THANKS.search(said):
        return "不客气～如果还想比较参数或者查物流，随时喊我。"
    if _BYE.search(said):
        return "好的，随时回来找我，祝你购物愉快！"
    if _IDENTITY.search(said):
        return (
            "我是 ShopMate 的智能导购兼客服，可以按预算和场景推荐商品、对比参数，"
            "也能查订单和物流，解答退换货、发票、保修这些政策问题。"
        )
    if _OFFTOPIC.search(said):
        return "这个我可能帮不上忙，不过挑商品、查订单、处理售后我都挺熟的，要不要试试？"
    if _GREETING.search(said):
        return SMALLTALK_REPLIES[Intent.SMALLTALK_OR_UNKNOWN]
    return "我在的。你想找商品、查订单物流，还是问退换货政策？直接说就行。"


__all__ = [
    "compose_compare",
    "compose_order_status",
    "compose_product_detail",
    "compose_product_discovery",
    "compose_purchase_intro",
    "compose_return_eligibility",
    "compose_shipment",
    "compose_smalltalk",
]
