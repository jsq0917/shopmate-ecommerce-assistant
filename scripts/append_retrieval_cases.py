"""Append the stage-C retrieval gold cases (x2-*) to data/eval/retrieval_cases.jsonl.

Existing 58 rows are preserved byte-for-byte; the new rows are verified before
writing:
  * case_id uniqueness against the existing file
  * every expected_phrase exists verbatim in the parsed chunks of the
    (title, expected_version) document that will actually be indexed
  * the expected_version's effective window covers the case's ``at``
  * forbidden_versions that still contain the phrase are reported (a leak there
    is still caught by the version_leaks metric, but we want to know)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

CORPUS = json.loads(Path("corpus_dump.json").read_text(encoding="utf-8"))
CASES_PATH = Path("data/eval/retrieval_cases.jsonl")

# (title, version) -> concatenated chunk text of that document version
TEXT: dict[tuple[str, str], str] = {}
WINDOW: dict[tuple[str, str], tuple[datetime, datetime | None]] = {}
for _key, doc in CORPUS.items():
    version = doc["version"]
    title = doc["title"]
    TEXT[(title, version)] = "\n".join(c["text"] for c in doc["chunks"])
    start = datetime.fromisoformat(doc["effective_from"].replace("Z", "+00:00"))
    end = (
        datetime.fromisoformat(doc["effective_to"].replace("Z", "+00:00"))
        if doc["effective_to"]
        else None
    )
    WINDOW[(title, version)] = (start, end)

# version -> set of versions of the same document family (for leak reporting)
FAMILY_VERSIONS: dict[str, set[str]] = {}
for key in CORPUS:
    fam, _, version = key.rpartition("@")
    FAMILY_VERSIONS.setdefault(fam, set()).add(version)

NOW = "2026-10-19T00:00:00Z"
MID = "2026-09-15T00:00:00Z"  # base docs -> 2026.07.1, category/SG docs -> 2026.08.1
Y25 = "2025-05-01T00:00:00Z"  # category docs -> 2025.1
Y24 = "2024-06-01T00:00:00Z"  # category docs -> 2024.1
CROSS_SHOP = "00000000-0000-0000-0000-0000000000ff"
CONFLICT_KB = "eval-conflict"


def case(
    cid: str,
    category: str,
    question: str,
    *,
    at: str = NOW,
    split: str,
    titles: tuple[str, ...] = (),
    version: str | None = None,
    phrases: tuple[str, ...] = (),
    forbidden_titles: tuple[str, ...] = (),
    forbidden_versions: tuple[str, ...] = (),
    should_answer: bool = True,
    expect_conflict: bool = False,
    region: str = "CN",
    shop: str = "demo",
    knowledge_base: str | None = None,
) -> dict:
    return {
        "at": at,
        "case_id": cid,
        "category": category,
        "expect_conflict": expect_conflict,
        "expected_phrases": list(phrases),
        "expected_titles": list(titles),
        "expected_version": version,
        "forbidden_titles": list(forbidden_titles),
        "forbidden_versions": list(forbidden_versions),
        "knowledge_base": knowledge_base,
        "locale": "zh-CN",
        "question": question,
        "region": region,
        "shop": shop,
        "should_answer": should_answer,
        "split": split,
    }


NEW: list[dict] = []

# ---------------------------------------------------------------- normal (13)
NEW += [
    case(
        "x2-normal-01",
        "normal",
        "衣服拉链坏了能保修吗？",
        split="dev",
        titles=("服饰质量保修条款",),
        version="2026.10.1",
        phrases=("拉链、纽扣、按扣与挂钩等五金件自签收之日起 6 个月内出现损坏的，可申请保修",),
        forbidden_versions=("2026.08.1",),
    ),
    case(
        "x2-normal-02",
        "normal",
        "手机电池不耐用能申请检测更换吗？",
        split="test",
        titles=("数码三包与保修条款",),
        version="2026.10.1",
        phrases=("电池在保修期内最大容量低于标称值百分之八十时，可申请检测更换",),
        forbidden_versions=("2026.08.1",),
    ),
    case(
        "x2-normal-03",
        "normal",
        "数码商品退货时数据会被清除吗？",
        split="dev",
        titles=("数码商品退换货政策",),
        version="2026.10.1",
        phrases=("商城在验收时出具数据清除报告",),
        forbidden_versions=("2026.08.1",),
    ),
    case(
        "x2-normal-04",
        "normal",
        "床垫弹簧塌陷了能申请检测吗？",
        split="test",
        titles=("家居结构保修与保养要求",),
        version="2026.10.1",
        phrases=("床垫弹簧塌陷在 24 个月内可申请检测，按检测结论处理",),
        forbidden_versions=("2026.08.1",),
    ),
    case(
        "x2-normal-05",
        "normal",
        "家具安装后发现连接件松动，还能免费复紧吗？",
        split="dev",
        titles=("家居送货与安装服务说明",),
        version="2026.10.1",
        phrases=("复紧需在安装完成之日起十四日内提出",),
        forbidden_versions=("2026.08.1",),
    ),
    case(
        "x2-normal-06",
        "normal",
        "大件家具退货上门取件要收费吗？",
        split="test",
        titles=("大件家居退换货政策",),
        version="2026.10.1",
        phrases=("每笔订单首次取件免收服务费，再次取件收取 50 元",),
        forbidden_versions=("2026.08.1",),
    ),
    case(
        "x2-normal-07",
        "normal",
        "大件家居能无理由退货吗？要多久内？",
        split="dev",
        titles=("大件家居退换货政策",),
        version="2026.10.1",
        phrases=(
            "消费者自签收之日起 15 日内，可以在商品未安装、未使用、包装齐全的前提下申请无理由退货",
        ),
        forbidden_versions=("2026.08.1",),
    ),
    case(
        "x2-normal-08",
        "normal",
        "M 码适合什么身材？",
        split="test",
        titles=("服饰尺码对照与试穿报告",),
        version="2026.10.1",
        phrases=("身高 164 至 168 厘米、胸围 84 厘米左右",),
        forbidden_versions=("2026.08.1",),
    ),
    case(
        "x2-normal-09",
        "normal",
        "服饰类订单多久内可以补开发票？",
        split="dev",
        titles=("服饰发票与价保规则",),
        version="2026.10.1",
        phrases=("服饰类订单完成后 90 日内可申请补开发票，超期需人工评估",),
        forbidden_versions=("2026.08.1",),
    ),
    case(
        "x2-normal-10",
        "normal",
        "数码类订单多久内可以补开发票？",
        split="test",
        titles=("数码发票与价保规则",),
        version="2026.10.1",
        phrases=("数码类订单完成后 90 日内可申请补开发票，超期需人工评估",),
        forbidden_versions=("2026.08.1",),
    ),
    case(
        "x2-normal-11",
        "normal",
        "家居类商品多久内可以补开发票？",
        split="dev",
        titles=("家居发票与价保规则",),
        version="2026.10.1",
        phrases=("家居类订单完成后 90 日内可申请补开发票，超期需人工评估",),
        forbidden_versions=("2026.08.1",),
    ),
    case(
        "x2-normal-12",
        "normal",
        "换货的数码商品能申请数据迁移协助吗？",
        split="test",
        titles=("数码数据备份与迁移指引",),
        version="2026.10.1",
        phrases=("每笔订单首次换货可申请一次免费的云端迁移协助，由售后远程指导",),
        forbidden_versions=("2026.08.1",),
    ),
    case(
        "x2-normal-13",
        "normal",
        "个护商品未拆封能退吗？",
        split="dev",
        titles=("个护与卫生类商品售后规则",),
        version="2026.10.1",
        phrases=("未拆封商品可无理由退货",),
        forbidden_versions=("2026.07.1",),
    ),
]

# ------------------------------------------------------------ exact_fact (10)
NEW += [
    case(
        "x2-exact-01",
        "exact_fact",
        "机械键盘的保修期是多久？",
        split="test",
        titles=("商品保修政策",),
        version="2026.10.1",
        phrases=("机械键盘与部分智能手表保修二十四个月",),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-exact-02",
        "exact_fact",
        "补开发票的期限是多久？",
        split="dev",
        titles=("发票开具与补开规则",),
        version="2026.10.1",
        phrases=("订单完成后的九十日内可以申请补开发票，超过九十日需通过人工工单评估",),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-exact-03",
        "exact_fact",
        "价保的期限是多久？",
        split="test",
        titles=("价格保护政策",),
        version="2026.10.1",
        phrases=("自订单支付成功之日起七日内，同一商品在同一店铺出现降价时，可以申请价格保护",),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-exact-04",
        "exact_fact",
        "货到付款单笔金额上限是多少？",
        split="dev",
        titles=("货到付款规则",),
        version="2026.10.1",
        phrases=("货到付款仅支持中国大陆地区部分城市，单笔订单金额不得超过 2000 元",),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-exact-05",
        "exact_fact",
        "哪些商品支持分期？支持几期？",
        split="test",
        titles=("分期付款说明",),
        version="2026.10.1",
        phrases=("部分商品支持 3 期、6 期与 12 期分期，具体期数以结算页展示为准",),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-exact-06",
        "exact_fact",
        "积分抵扣上限是多少？",
        split="dev",
        titles=("积分规则",),
        version="2026.10.1",
        phrases=("100 积分可抵扣 1 元，单笔订单最多抵扣订单金额的 20%",),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-exact-07",
        "exact_fact",
        "偏远地区配送附加费怎么收？",
        split="test",
        titles=("偏远地区配送附加费说明",),
        version="2026.10.1",
        phrases=(
            "偏远地区订单按重量收取附加费，首重 1 "
            "公斤 12 元，续重每公斤 8 元，具体金额以结算页为准",
        ),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-exact-08",
        "exact_fact",
        "定制商品的生产周期是多久？",
        split="dev",
        titles=("定制商品售后规则",),
        version="2026.10.1",
        phrases=("定制商品的生产周期为七至十五个工作日，遇节假日顺延",),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-exact-09",
        "exact_fact",
        "活动期间未支付的订单多久释放库存？",
        split="test",
        titles=("促销活动通用规则",),
        version="2026.10.1",
        phrases=("活动期间下单未支付的订单在三十一分钟后自动释放库存",),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-exact-10",
        "exact_fact",
        "非质量问题的换货要在多久内提出？",
        split="dev",
        titles=("换货政策",),
        version="2026.10.1",
        phrases=(
            "非质量问题换货需在签收之日起七日内提出，商品需保持完好且不影响二次销售，来回运费由消费者承担",
        ),
        forbidden_versions=("2026.07.1",),
    ),
]

# ------------------------------------------- expired / version pairs (35)
# at=2026-09-15: base docs -> 2026.07.1, category/SG docs -> 2026.08.1
NEW += [
    case(
        "x2-ver-01",
        "expired",
        "价保的期限是多久？",
        at=MID,
        split="test",
        titles=("价格保护政策",),
        version="2026.07.1",
        phrases=("自订单支付成功之日起三日内，同一商品在同一店铺出现降价时，可以申请价格保护",),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-02",
        "expired",
        "补开发票的期限是多久？",
        at=MID,
        split="dev",
        titles=("发票开具与补开规则",),
        version="2026.07.1",
        phrases=("订单完成后的六十日内可以申请补开发票，超过六十日需通过人工工单评估",),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-03",
        "expired",
        "订单满多少可以包邮？",
        at=MID,
        split="test",
        titles=("包邮门槛说明",),
        version="2026.07.1",
        phrases=(
            "单笔订单实付金额满 129 元即可享受普通"
            "快递包邮，门槛按实付金额计算，不含运费与增值服务费",
        ),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-04",
        "expired",
        "货到付款单笔金额上限是多少？",
        at=MID,
        split="dev",
        titles=("货到付款规则",),
        version="2026.07.1",
        phrases=("货到付款仅支持中国大陆地区部分城市，单笔订单金额不得超过 1000 元",),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-05",
        "expired",
        "机械键盘的保修期是多久？",
        at=MID,
        split="test",
        titles=("商品保修政策",),
        version="2026.07.1",
        phrases=("机械键盘与部分智能手表保修十二个月",),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-06",
        "expired",
        "退款一般多久到账？",
        at=MID,
        split="dev",
        titles=("退款到账时效说明",),
        version="2026.07.1",
        phrases=("原路退回的退款通常在发起后三至十个工作日内到账，具体取决于支付渠道",),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-07",
        "expired",
        "服饰退货要检测多久？",
        at=MID,
        split="test",
        titles=("服饰退换货政策（中国大陆）",),
        version="2026.08.1",
        phrases=("仓库签收后 三个工作日内 完成检验",),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-08",
        "expired",
        "服饰类订单多久内可以补开发票？",
        at=MID,
        split="dev",
        titles=("服饰发票与价保规则",),
        version="2026.08.1",
        phrases=("服饰类订单完成后 45 日内可申请补开发票，超期需人工评估",),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-09",
        "expired",
        "数码类订单多久内可以补开发票？",
        at=MID,
        split="test",
        titles=("数码发票与价保规则",),
        version="2026.08.1",
        phrases=("数码类订单完成后 45 日内可申请补开发票，超期需人工评估",),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-10",
        "expired",
        "家居类商品多久内可以补开发票？",
        at=MID,
        split="dev",
        titles=("家居发票与价保规则",),
        version="2026.08.1",
        phrases=("家居类订单完成后 45 日内可申请补开发票，超期需人工评估",),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-11",
        "expired",
        "家具到货就损坏，多久内可以退换？",
        at=MID,
        split="test",
        titles=("大件家居退换货政策",),
        version="2026.08.1",
        phrases=("商品到货即损坏、结构失稳或部件缺失的，自签收之日起 15 日内可申请退换货",),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-12",
        "expired",
        "家居保修检测周期是多久？",
        at=MID,
        split="dev",
        titles=("家居结构保修与保养要求",),
        version="2026.08.1",
        phrases=(
            "消费者提交订单号与损坏照片后，由售后确认是否上门检测，检测周期为 五至七个工作日",
        ),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-13",
        "expired",
        "数码送修前有几天完成数据备份？",
        at=MID,
        split="test",
        titles=("数码数据备份与迁移指引",),
        version="2026.08.1",
        phrases=("送修申请提交后，消费者有 五日 时间完成数据备份与清除",),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-14",
        "expired",
        "衣服拉链坏了能保修吗？",
        at=MID,
        split="dev",
        titles=("服饰质量保修条款",),
        version="2026.08.1",
        phrases=("拉链、纽扣、按扣与挂钩等五金件自签收之日起 3 个月内出现损坏的，可申请保修",),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-15",
        "expired",
        "数码产品的电池和屏幕保修多久？",
        at=MID,
        split="test",
        titles=("数码三包与保修条款",),
        version="2026.08.1",
        phrases=("主机自签收之日起 12 个月内保修，电池 6 个月，屏幕 6 个月，随附配件 3 个月",),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-16",
        "expired",
        "大件家居能无理由退货吗？要多久内？",
        at=MID,
        split="dev",
        titles=("大件家居退换货政策",),
        version="2026.08.1",
        phrases=(
            "消费者自签收之日起 7 日内，可以在商品未安装、未使用、包装齐全的前提下申请无理由退货",
        ),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-17",
        "expired",
        "新加坡订单的退货期限是多久？",
        at=MID,
        split="test",
        region="SG",
        titles=("退货与退款政策（新加坡）",),
        version="2026.08.1",
        phrases=("消费者自签收之日起七日内可申请退货，商品需保持完好并附原包装",),
        forbidden_versions=("2026.10.1",),
    ),
    case(
        "x2-ver-18",
        "expired",
        "新加坡满多少包邮？运费多少？",
        at=MID,
        split="dev",
        region="SG",
        titles=("配送政策（新加坡）",),
        version="2026.08.1",
        phrases=("标准配送为五至十个工作日，满 150 新元包邮，未满收取 10 新元运费",),
        forbidden_versions=("2026.10.1",),
    ),
]

# at=2025-05-01: category docs -> 2025.1
NEW += [
    case(
        "x2-ver-19",
        "expired",
        "服饰退货要检测多久？",
        at=Y25,
        split="test",
        titles=("服饰退换货政策（中国大陆）",),
        version="2025.1",
        phrases=("仓库签收后 四个工作日内 完成检验",),
    ),
    case(
        "x2-ver-20",
        "expired",
        "服饰类订单多久内可以补开发票？",
        at=Y25,
        split="dev",
        titles=("服饰发票与价保规则",),
        version="2025.1",
        phrases=("服饰类订单完成后 60 日内可申请补开发票，超期需人工评估",),
    ),
    case(
        "x2-ver-21",
        "expired",
        "数码类订单多久内可以补开发票？",
        at=Y25,
        split="test",
        titles=("数码发票与价保规则",),
        version="2025.1",
        phrases=("数码类订单完成后 60 日内可申请补开发票，超期需人工评估",),
    ),
    case(
        "x2-ver-22",
        "expired",
        "家居类商品多久内可以补开发票？",
        at=Y25,
        split="dev",
        titles=("家居发票与价保规则",),
        version="2025.1",
        phrases=("家居类订单完成后 60 日内可申请补开发票，超期需人工评估",),
    ),
    case(
        "x2-ver-23",
        "expired",
        "家具到货就损坏，多久内可以退换？",
        at=Y25,
        split="test",
        titles=("大件家居退换货政策",),
        version="2025.1",
        phrases=("商品到货即损坏、结构失稳或部件缺失的，自签收之日起 10 日内可申请退换货",),
    ),
    case(
        "x2-ver-24",
        "expired",
        "家居保修检测周期是多久？",
        at=Y25,
        split="dev",
        titles=("家居结构保修与保养要求",),
        version="2025.1",
        phrases=(
            "消费者提交订单号与损坏照片后，由售后确认是否上门检测，检测周期为 七至十个工作日",
        ),
    ),
    case(
        "x2-ver-25",
        "expired",
        "数码送修前有几天完成数据备份？",
        at=Y25,
        split="test",
        titles=("数码数据备份与迁移指引",),
        version="2025.1",
        phrases=("送修申请提交后，消费者有 三日 时间完成数据备份与清除",),
    ),
    case(
        "x2-ver-26",
        "expired",
        "服饰保修检测要多久？",
        at=Y25,
        split="dev",
        titles=("服饰质量保修条款",),
        version="2025.1",
        phrases=(
            "消费者提交订单号与损坏照片后，由售后确认是否进入检测流程，检测周期为 五至七个工作日",
        ),
    ),
    case(
        "x2-ver-27",
        "expired",
        "试穿报告的有效期是多久？",
        at=Y25,
        split="test",
        titles=("服饰尺码对照与试穿报告",),
        version="2025.1",
        phrases=("商品页提供的试穿报告由不同身形的试穿志愿者填写，有效期为 45 日",),
    ),
]

# at=2024-06-01: category docs -> 2024.1
NEW += [
    case(
        "x2-ver-28",
        "expired",
        "服饰类订单多久内可以补开发票？",
        at=Y24,
        split="dev",
        titles=("服饰发票与价保规则",),
        version="2024.1",
        phrases=("服饰类订单完成后 30 日内可申请补开发票，超期需人工评估",),
        forbidden_versions=("2025.1",),
    ),
    case(
        "x2-ver-29",
        "expired",
        "数码类订单多久内可以补开发票？",
        at=Y24,
        split="test",
        titles=("数码发票与价保规则",),
        version="2024.1",
        phrases=("数码类订单完成后 30 日内可申请补开发票，超期需人工评估",),
        forbidden_versions=("2025.1",),
    ),
    case(
        "x2-ver-30",
        "expired",
        "家居类商品多久内可以补开发票？",
        at=Y24,
        split="dev",
        titles=("家居发票与价保规则",),
        version="2024.1",
        phrases=("家居类订单完成后 30 日内可申请补开发票，超期需人工评估",),
        forbidden_versions=("2025.1",),
    ),
    case(
        "x2-ver-31",
        "expired",
        "家具到货就损坏，多久内可以退换？",
        at=Y24,
        split="test",
        titles=("大件家居退换货政策",),
        version="2024.1",
        phrases=("商品到货即损坏、结构失稳或部件缺失的，自签收之日起 7 日内可申请退换货",),
        forbidden_versions=("2025.1",),
    ),
    case(
        "x2-ver-32",
        "expired",
        "床垫弹簧塌陷了能申请检测吗？",
        at=Y24,
        split="dev",
        titles=("家居结构保修与保养要求",),
        version="2024.1",
        phrases=("床垫弹簧塌陷在 6 个月内可申请检测，按检测结论处理",),
        forbidden_versions=("2025.1",),
    ),
    case(
        "x2-ver-33",
        "expired",
        "数码产品的电池和屏幕保修多久？",
        at=Y24,
        split="test",
        titles=("数码三包与保修条款",),
        version="2024.1",
        phrases=("主机自签收之日起 12 个月内保修，电池 6 个月，屏幕 3 个月，随附配件 3 个月",),
        forbidden_versions=("2025.1",),
    ),
    case(
        "x2-ver-34",
        "expired",
        "M 码适合什么身材？",
        at=Y24,
        split="dev",
        titles=("服饰尺码对照与试穿报告",),
        version="2024.1",
        phrases=("身高 164 至 168 厘米、胸围 90 厘米左右",),
        forbidden_versions=("2025.1",),
    ),
    case(
        "x2-ver-35",
        "expired",
        "家居保修检测周期是多久？",
        at=Y24,
        split="test",
        titles=("家居结构保修与保养要求",),
        version="2024.1",
        phrases=(
            "消费者提交订单号与损坏照片后，由售后确认是否上门检测，检测周期为 十至十五个工作日",
        ),
        forbidden_versions=("2025.1",),
    ),
]

# ------------------------------------------------------- near_dup (10)
NEW += [
    case(
        "x2-near-01",
        "near_dup_hard",
        "保修检测一般要多久？",
        split="dev",
        titles=("商品保修政策",),
        version="2026.10.1",
        phrases=("检测周期一般为五至七个工作日",),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-near-02",
        "near_dup_hard",
        "衣服色差明显能退吗？",
        split="test",
        titles=("服饰退换货政策（中国大陆）",),
        version="2026.10.1",
        phrases=("色差超出行业公差（色差 ΔE 大于 3.0）时视为质量问题",),
    ),
    case(
        "x2-near-03",
        "near_dup",
        "退货之后退款多久到账？",
        split="dev",
        titles=("退款到账时效说明",),
        version="2026.10.1",
        phrases=("原路退回的退款通常在发起后一至七个工作日内到账，具体取决于支付渠道",),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-near-04",
        "near_dup_hard",
        "数码产品的电池和屏幕保修多久？",
        split="test",
        titles=("数码三包与保修条款",),
        version="2026.10.1",
        phrases=("主机自签收之日起 12 个月内保修，电池 12 个月，屏幕 6 个月，随附配件 6 个月",),
        forbidden_versions=("2026.08.1",),
    ),
    case(
        "x2-near-05",
        "near_dup",
        "大件商品退货谁上门取件？收费吗？",
        split="dev",
        titles=("大件家居退换货政策",),
        version="2026.10.1",
        phrases=("大件退货由上门的承运商取件，每笔订单首次取件免收服务费，再次取件收取 50 元",),
        forbidden_versions=("2026.08.1",),
    ),
    case(
        "x2-near-06",
        "near_dup",
        "包裹一直没物流更新怎么办？",
        split="test",
        titles=("丢件与破损处理流程",),
        version="2026.10.1",
        phrases=("物流信息超过七十二小时无更新时，可提交丢件核查，承运商核查周期为三至七个工作日",),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-near-07",
        "near_dup_hard",
        "定制商品能退吗？",
        split="dev",
        titles=("定制商品售后规则",),
        version="2026.10.1",
        phrases=("定制商品出现质量问题或与确认稿不一致时，可在签收后十五日内申请返修、重做或退货",),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-near-08",
        "near_dup",
        "优惠券过期了还能用吗？",
        split="test",
        titles=("优惠券使用规则",),
        version="2026.10.1",
        phrases=("已过期优惠券在任何情况下都不补发",),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-near-09",
        "near_dup",
        "未成年人信息会被收集吗？",
        split="dev",
        titles=("隐私与个人信息保护说明",),
        version="2026.10.1",
        phrases=("未满十八周岁的用户应在监护人同意下使用本服务，商城不主动收集未成年人信息",),
        forbidden_versions=("2026.07.1",),
    ),
    case(
        "x2-near-10",
        "near_dup",
        "上门安装收费吗？怎么预约？",
        split="test",
        titles=("家居送货与安装服务说明",),
        version="2026.10.1",
        phrases=("安装服务需在送货时一并预约，安装费按件计收，费用在结算页展示",),
    ),
]

# ------------------------------------------------------- no_answer (8)
NEW += [
    case(
        "x2-noans-01",
        "no_answer",
        "手机屏幕碎了能走碎屏险吗？怎么购买？",
        split="dev",
        should_answer=False,
    ),
    case("x2-noans-02", "no_answer", "新家具有除甲醛服务吗？", split="test", should_answer=False),
    case(
        "x2-noans-03", "no_answer", "能预约上门量体定制西装吗？", split="dev", should_answer=False
    ),
    case(
        "x2-noans-04",
        "no_answer",
        "有旧衣回收服务吗？旧衣服能抵现吗？",
        split="test",
        should_answer=False,
    ),
    case(
        "x2-noans-05", "no_answer", "支持以租代购吗？我想先租后买", split="dev", should_answer=False
    ),
    case(
        "x2-noans-06",
        "no_answer",
        "可以用支票付款吗？支持传真下单吗？",
        split="test",
        should_answer=False,
    ),
    case(
        "x2-noans-07",
        "no_answer",
        "能电话下单吗？客服电话是多少？",
        split="dev",
        should_answer=False,
    ),
    case(
        "x2-noans-08",
        "no_answer",
        "延保服务怎么购买？原厂延保多少钱？",
        split="test",
        should_answer=False,
    ),
]

# ------------------------------------------------------- cross_shop (4)
NEW += [
    case(
        "x2-cross-01",
        "cross_shop",
        "衣服拉链坏了能保修吗？",
        split="test",
        shop=CROSS_SHOP,
        should_answer=False,
        forbidden_titles=("服饰质量保修条款",),
    ),
    case(
        "x2-cross-02",
        "cross_shop",
        "补开发票的期限是多久？",
        split="dev",
        shop=CROSS_SHOP,
        should_answer=False,
        forbidden_titles=("发票开具与补开规则",),
    ),
    case(
        "x2-cross-03",
        "cross_shop",
        "会员积分抵扣上限是多少？",
        split="test",
        shop=CROSS_SHOP,
        should_answer=False,
        forbidden_titles=("积分规则",),
    ),
    case(
        "x2-cross-04",
        "cross_shop",
        "大件家具退货上门取件要收费吗？",
        split="dev",
        shop=CROSS_SHOP,
        should_answer=False,
        forbidden_titles=("大件家居退换货政策",),
    ),
]

# ------------------------------------------------------- conflict (2)
# The fixture holds two overlapping versions (10% proportional vs flat 20 yuan);
# the phrase below is shared by both so the gold check survives the conflict.
CONFLICT_PHRASE = "手续费从退款金额中直接扣除，并在退款明细中单独列示。"
NEW += [
    case(
        "x2-conf-01",
        "conflict",
        "退货手续费是多少钱？",
        split="test",
        titles=("退货手续费说明（评测冲突样本）",),
        phrases=(CONFLICT_PHRASE,),
        should_answer=False,
        expect_conflict=True,
        knowledge_base=CONFLICT_KB,
    ),
    case(
        "x2-conf-02",
        "conflict",
        "退货手续费如何收取？",
        split="dev",
        titles=("退货手续费说明（评测冲突样本）",),
        phrases=(CONFLICT_PHRASE,),
        should_answer=False,
        expect_conflict=True,
        knowledge_base=CONFLICT_KB,
    ),
]

# ------------------------------------------------------------------ checks
existing_lines = [
    line for line in CASES_PATH.read_text(encoding="utf-8").splitlines() if line.strip()
]
existing_ids = {json.loads(line)["case_id"] for line in existing_lines}

errors: list[str] = []
seen: set[str] = set()
for row in NEW:
    cid = row["case_id"]
    if cid in existing_ids or cid in seen:
        errors.append(f"duplicate case_id: {cid}")
    seen.add(cid)

    at = datetime.fromisoformat(row["at"].replace("Z", "+00:00"))
    if row["knowledge_base"] == CONFLICT_KB:
        # The conflict fixtures live outside POLICY_DOCS: they are ingested and
        # removed again by the evaluator itself. Verify against the fixture files.
        fixture_text = "\n".join(
            p.read_text(encoding="utf-8") for p in sorted(Path("data/eval/conflict").glob("*.md"))
        )
        for phrase in row["expected_phrases"]:
            if phrase not in fixture_text:
                errors.append(f"{cid}: phrase not in conflict fixtures: {phrase[:40]}")
        continue
    for title in row["expected_titles"]:
        key = (title, row["expected_version"])
        if key not in TEXT:
            errors.append(f"{cid}: unknown document {title}@{row['expected_version']}")
            continue
        start, end = WINDOW[key]
        if not (start <= at and (end is None or at < end)):
            errors.append(
                f"{cid}: at {row['at']} outside window of {title}@{row['expected_version']}"
            )
        text = TEXT[key]
        for phrase in row["expected_phrases"]:
            if phrase not in text:
                errors.append(
                    f"{cid}: phrase not in {title}@{row['expected_version']}: {phrase[:40]}"
                )
        for bad in row["forbidden_versions"]:
            bad_key = (title, bad)
            if bad_key in TEXT:
                hits = [p for p in row["expected_phrases"] if p in TEXT[bad_key]]
                if hits:
                    print(
                        f"[info] {cid}: forbidden {bad} still contains "
                        f"{len(hits)} phrase(s) (version_leaks metric still applies)"
                    )

if errors:
    print("FAILED:")
    for line in errors:
        print(" ", line)
    raise SystemExit(1)

# ------------------------------------------------------------------ write
with CASES_PATH.open("a", encoding="utf-8", newline="\n") as handle:
    for row in NEW:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

total = len(existing_lines) + len(NEW)
dev = sum(
    1
    for line in existing_lines + [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in NEW]
    if json.loads(line)["split"] == "dev"
)
test = total - dev
print(f"existing={len(existing_lines)} appended={len(NEW)} total={total} dev={dev} test={test}")
cats: dict[str, int] = {}
for row in NEW:
    cats[row["category"]] = cats.get(row["category"], 0) + 1
print("new categories:", dict(sorted(cats.items())))
