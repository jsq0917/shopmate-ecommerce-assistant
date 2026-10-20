"""Deterministic answer composition for the chat path.

The composer turns verified tool facts into a plain-Chinese answer. It never invents a
price, stock number or status: every number it prints was produced by a tool and passed in
here. Money is always shown from ``*_cents`` as a whole-yuan amount, never a float.
"""

from __future__ import annotations

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


def compose_product_discovery(cards: list[Mapping[str, Any]]) -> str:
    """Return a recommendation list built only from the search cards."""
    if not cards:
        return "没有找到符合你要求的商品，可以换个关键词或放宽预算再试试。"
    lines = ["为你找到以下几款："]
    for index, card in enumerate(cards[:5], start=1):
        price = _yuan(int(card["price_cents"]))
        stock = _stock_inline(card["stock_status"], card.get("available_qty"))
        lines.append(f"{index}. {card['title']}（¥{price}，{stock}）")
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
        "created": "已创建",
        "paid": "已支付",
        "processing": "处理中",
        "shipped": "已发货",
        "delivered": "已签收",
        "completed": "已完成",
        "cancelled": "已取消",
    }
    status = status_map.get(str(data["status"]), str(data["status"]))
    total = _yuan(int(data["total_cents"]))
    return f"订单 {data['order_no']} 当前状态：{status}，订单金额 ¥{total}。"


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
        return f"该商品符合退货条件。需要准备：{materials}。确认后即可提交退货申请。"
    if decision == "ineligible":
        code = str(data.get("decision_code") or "")
        reasons = {
            "RETURN_WINDOW_EXPIRED": "已超过签收后 7 天的退货窗口。",
            "DUPLICATE_RETURN": "该商品已有进行中的退货申请。",
            "RETURN_NOT_ALLOWED": "该商品不支持自助退货。",
            "INVALID_STATE": "当前订单状态不支持退货。",
            "ORDER_NOT_FOUND": "未找到可退货的订单或商品。",
        }
        return reasons.get(code, "该商品当前不符合自助退货条件。")
    if decision == "needs_clarification":
        return "还需要确认一下退货原因，请补充说明商品的具体问题。"
    return "该退货需要人工核实，已为你准备转人工入口。"


SMALLTALK_REPLIES: dict[Intent, str] = {
    Intent.SMALLTALK_OR_UNKNOWN: (
        "你好！我可以帮你查商品、订单物流、退货政策和转人工，请问需要什么帮助？"
    ),
}


def compose_smalltalk(intent: Intent, clarification_text: str | None) -> str:
    """Return a safe, on-topic reply for smalltalk or a clarifying question."""
    if clarification_text:
        return clarification_text
    return SMALLTALK_REPLIES.get(intent, "请问有什么可以帮你？")


__all__ = [
    "compose_compare",
    "compose_order_status",
    "compose_product_detail",
    "compose_product_discovery",
    "compose_return_eligibility",
    "compose_shipment",
    "compose_smalltalk",
]
