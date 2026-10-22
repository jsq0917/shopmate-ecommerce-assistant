"""Deterministic synthetic commerce dataset.

All values are invented. Brand names, people, addresses and tracking numbers are fictional
and must never be replaced with real customer data.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shopmate_ecommerce_assistant.core.ids import stable_uuid

SEED = 20261019
ANCHOR = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
CURRENCY = "CNY"
WAREHOUSE = "WH-SH-01"

SHOP_NAME = "ShopMate 示例商城（合成数据）"


@dataclass(frozen=True, slots=True)
class ProductSpec:
    """Curated catalog definition used to derive rows deterministically."""

    slug: str
    title: str
    brand: str
    category: str
    description: str
    attributes: dict[str, Any]
    variants: tuple[tuple[str, int], ...]
    returnable: bool = True


PRODUCTS: tuple[ProductSpec, ...] = (
    ProductSpec(
        "sl-nc700",
        "声岚 SL-NC700 头戴式主动降噪耳机",
        "声岚",
        "降噪耳机",
        "双馈降噪配合 40 小时续航，适合通勤与长时间办公佩戴。",
        {
            "connectivity": "蓝牙 5.3",
            "battery_hours": 40,
            "noise_cancelling": True,
            "weight_g": 265,
            "warranty_months": 12,
        },
        (("曜石黑", 89900), ("雾银白", 89900)),
    ),
    ProductSpec(
        "sl-nc500",
        "声岚 SL-NC500 轻量头戴降噪耳机",
        "声岚",
        "降噪耳机",
        "轻量化头梁与混合降噪，通勤场景下可折叠收纳，续航 32 小时。",
        {
            "connectivity": "蓝牙 5.2",
            "battery_hours": 32,
            "noise_cancelling": True,
            "weight_g": 235,
            "warranty_months": 12,
        },
        (("曜石黑", 59900), ("雾银白", 59900), ("松石绿", 61900)),
    ),
    ProductSpec(
        "sl-nc300",
        "声岚 SL-NC300 入耳式降噪耳机",
        "声岚",
        "降噪耳机",
        "入耳式主动降噪，单次续航 8 小时，配合充电盒共 24 小时。",
        {
            "connectivity": "蓝牙 5.3",
            "battery_hours": 24,
            "noise_cancelling": True,
            "weight_g": 48,
            "warranty_months": 12,
        },
        (("曜石黑", 29900), ("雾银白", 29900)),
    ),
    ProductSpec(
        "sl-buds-air",
        "声岚 SL-BUDS Air 真无线蓝牙耳机",
        "声岚",
        "蓝牙耳机",
        "半入耳设计，通话降噪，单次续航 6 小时，充电盒总计 24 小时。",
        {
            "connectivity": "蓝牙 5.2",
            "battery_hours": 24,
            "noise_cancelling": False,
            "weight_g": 42,
            "warranty_months": 12,
        },
        (("云雾白", 24900), ("曜石黑", 24900)),
    ),
    ProductSpec(
        "sl-buds-lite",
        "声岚 SL-BUDS Lite 真无线耳机",
        "声岚",
        "蓝牙耳机",
        "入门款真无线耳机，支持触控操作，单次续航 5 小时。",
        {
            "connectivity": "蓝牙 5.0",
            "battery_hours": 20,
            "noise_cancelling": False,
            "weight_g": 40,
            "warranty_months": 12,
        },
        (("云雾白", 15900), ("曜石黑", 15900)),
    ),
    ProductSpec(
        "sl-buds-pro",
        "声岚 SL-BUDS Pro 真无线降噪耳机",
        "声岚",
        "蓝牙耳机",
        "入耳式真无线降噪，支持多设备切换，单次续航 7 小时。",
        {
            "connectivity": "蓝牙 5.3",
            "battery_hours": 28,
            "noise_cancelling": True,
            "weight_g": 52,
            "warranty_months": 18,
        },
        (("曜石黑", 42900), ("云雾白", 42900)),
    ),
    ProductSpec(
        "kc87",
        "键川 KC87 三模机械键盘",
        "键川",
        "机械键盘",
        "87 键紧凑布局，支持有线、蓝牙与 2.4G 三模连接，热插拔轴座。",
        {
            "layout": "87 键",
            "switch": "红轴",
            "connection": "三模",
            "backlight": "白色背光",
            "warranty_months": 24,
        },
        (("深空灰", 39900), ("奶白", 39900)),
    ),
    ProductSpec(
        "kc104",
        "键川 KC104 全尺寸机械键盘",
        "键川",
        "机械键盘",
        "104 键全尺寸布局，带独立数字区，适合财务与数据录入。",
        {
            "layout": "104 键",
            "switch": "茶轴",
            "connection": "有线",
            "backlight": "RGB",
            "warranty_months": 24,
        },
        (("深空灰", 45900),),
    ),
    ProductSpec(
        "kc68",
        "键川 KC68 便携机械键盘",
        "键川",
        "机械键盘",
        "68 键便携布局，支持蓝牙双设备切换，适合平板与笔记本。",
        {
            "layout": "68 键",
            "switch": "红轴",
            "connection": "三模",
            "backlight": "白色背光",
            "warranty_months": 24,
        },
        (("奶白", 32900), ("雾蓝", 32900)),
    ),
    ProductSpec(
        "kw200",
        "键川 KW200 无线薄膜键盘",
        "键川",
        "无线键盘",
        "2.4G 无线连接，静音按键，适合办公室长时间文字输入。",
        {
            "layout": "104 键",
            "switch": "薄膜",
            "connection": "2.4G",
            "battery_hours": 180,
            "warranty_months": 12,
        },
        (("深空灰", 19900),),
    ),
    ProductSpec(
        "gm-x1",
        "光影 GM-X1 无线鼠标",
        "光影",
        "无线鼠标",
        "轻量化机身，支持 2.4G 与蓝牙双模，续航约 60 天。",
        {
            "connection": "双模",
            "dpi": 4000,
            "weight_g": 78,
            "battery_days": 60,
            "warranty_months": 12,
        },
        (("深空灰", 12900), ("奶白", 12900)),
    ),
    ProductSpec(
        "gm-x2",
        "光影 GM-X2 人体工学无线鼠标",
        "光影",
        "无线鼠标",
        "人体工学侧握设计，支持多设备切换，适合长时间办公。",
        {
            "connection": "双模",
            "dpi": 8000,
            "weight_g": 96,
            "battery_days": 45,
            "warranty_months": 18,
        },
        (("深空灰", 18900),),
    ),
    ProductSpec(
        "gm-lite",
        "光影 GM-Lite 无线鼠标",
        "光影",
        "无线鼠标",
        "入门无线鼠标，即插即用，适合日常办公与网课。",
        {
            "connection": "2.4G",
            "dpi": 1600,
            "weight_g": 72,
            "battery_days": 90,
            "warranty_months": 12,
        },
        (("曜石黑", 7900),),
    ),
    ProductSpec(
        "pd65",
        "速派 PD65 氮化镓充电器",
        "速派",
        "充电器",
        "65W 氮化镓双口充电器，可同时为笔记本与手机供电。",
        {
            "power_w": 65,
            "ports": 2,
            "protocol": "PD3.0",
            "plug": "国标",
            "warranty_months": 12,
        },
        (("云雾白", 14900), ("曜石黑", 14900)),
    ),
    ProductSpec(
        "pd100",
        "速派 PD100 氮化镓充电器",
        "速派",
        "充电器",
        "100W 三口氮化镓充电器，支持笔记本快充与多设备分配。",
        {
            "power_w": 100,
            "ports": 3,
            "protocol": "PD3.1",
            "plug": "国标",
            "warranty_months": 12,
        },
        (("曜石黑", 22900),),
    ),
    ProductSpec(
        "qc30",
        "速派 QC30 快充充电器",
        "速派",
        "充电器",
        "30W 单口快充，体积小巧，适合出差携带。",
        {
            "power_w": 30,
            "ports": 1,
            "protocol": "QC4+",
            "plug": "国标",
            "warranty_months": 12,
        },
        (("云雾白", 7900),),
    ),
    ProductSpec(
        "pb20000",
        "速派 PB20000 移动电源",
        "速派",
        "移动电源",
        "20000mAh 容量，支持 22.5W 快充，可同时为两台设备充电。",
        {
            "capacity_mah": 20000,
            "power_w": 22,
            "ports": 2,
            "weight_g": 420,
            "warranty_months": 12,
        },
        (("深空灰", 19900),),
    ),
    ProductSpec(
        "pb10000",
        "速派 PB10000 移动电源",
        "速派",
        "移动电源",
        "10000mAh 轻薄移动电源，支持 20W 快充，可直接带上飞机。",
        {
            "capacity_mah": 10000,
            "power_w": 20,
            "ports": 1,
            "weight_g": 210,
            "warranty_months": 12,
        },
        (("云雾白", 12900), ("深空灰", 12900)),
    ),
    ProductSpec(
        "w1",
        "云栖 W1 智能手表",
        "云栖",
        "智能手表",
        "1.4 英寸屏幕，支持心率与睡眠监测，续航 14 天。",
        {
            "screen_inch": 1.4,
            "battery_days": 14,
            "water_resistance": "5ATM",
            "gps": True,
            "warranty_months": 12,
        },
        (("曜石黑", 99900), ("雾银白", 99900)),
    ),
    ProductSpec(
        "w1-se",
        "云栖 W1 SE 智能手表",
        "云栖",
        "智能手表",
        "轻量版智能手表，支持消息提醒与运动记录，续航 10 天。",
        {
            "screen_inch": 1.3,
            "battery_days": 10,
            "water_resistance": "3ATM",
            "gps": False,
            "warranty_months": 12,
        },
        (("曜石黑", 69900),),
    ),
    ProductSpec(
        "w2",
        "云栖 W2 智能手表",
        "云栖",
        "智能手表",
        "支持双频 GPS 与离线支付，续航 18 天，适合户外运动。",
        {
            "screen_inch": 1.5,
            "battery_days": 18,
            "water_resistance": "5ATM",
            "gps": True,
            "warranty_months": 24,
        },
        (("深空灰", 129900), ("松石绿", 129900)),
    ),
    ProductSpec(
        "sp-mini",
        "声岚 SP-Mini 蓝牙音箱",
        "声岚",
        "蓝牙音箱",
        "便携蓝牙音箱，支持 IPX5 防水，续航 12 小时。",
        {
            "power_w": 10,
            "battery_hours": 12,
            "waterproof": "IPX5",
            "weight_g": 380,
            "warranty_months": 12,
        },
        (("松石绿", 19900), ("曜石黑", 19900)),
    ),
    ProductSpec(
        "sp-pro",
        "声岚 SP-Pro 桌面蓝牙音箱",
        "声岚",
        "蓝牙音箱",
        "双单元立体声，支持 AUX 与蓝牙输入，适合桌面使用。",
        {
            "power_w": 30,
            "battery_hours": 16,
            "waterproof": "无",
            "weight_g": 1200,
            "warranty_months": 18,
        },
        (("深空灰", 49900),),
    ),
    ProductSpec(
        "cam-2k",
        "光影 CAM-2K 室内摄像头",
        "光影",
        "摄像头",
        "2K 分辨率，支持本地存储卡与移动侦测，适合家庭看护。",
        {
            "resolution": "2K",
            "night_vision": True,
            "storage": "TF 卡",
            "warranty_months": 12,
        },
        (("云雾白", 25900),),
    ),
    ProductSpec(
        "cam-4k",
        "光影 CAM-4K 室内摄像头",
        "光影",
        "摄像头",
        "4K 分辨率与双向语音，支持云台旋转，画面更清晰。",
        {
            "resolution": "4K",
            "night_vision": True,
            "storage": "TF 卡",
            "warranty_months": 18,
        },
        (("云雾白", 49900),),
    ),
    ProductSpec(
        "stand-a",
        "光影 Stand-A 桌面手机支架",
        "光影",
        "手机支架",
        "铝合金折叠支架，可调节角度，适配 4-7 英寸手机。",
        {"material": "铝合金", "foldable": True, "warranty_months": 6},
        (("深空灰", 4900), ("雾银白", 4900)),
    ),
    ProductSpec(
        "stand-mag",
        "光影 Stand-Mag 磁吸手机支架",
        "光影",
        "手机支架",
        "磁吸固定，支持横竖屏切换，兼容主流磁吸手机壳。",
        {"material": "铝合金", "magnetic": True, "warranty_months": 6},
        (("深空灰", 8900),),
    ),
    ProductSpec(
        "c2c-100w",
        "速派 C2C 100W 数据线",
        "速派",
        "数据线",
        "1.5 米编织线，支持 100W 供电与 480Mbps 数据传输。",
        {"length_m": 1.5, "power_w": 100, "connector": "USB-C to USB-C", "warranty_months": 12},
        (("曜石黑", 3900), ("云雾白", 3900)),
    ),
    ProductSpec(
        "l-20w",
        "速派 L 20W 数据线",
        "速派",
        "数据线",
        "1 米充电线，支持 20W 快充，适合日常备用。",
        {"length_m": 1.0, "power_w": 20, "connector": "USB-A to Lightning", "warranty_months": 6},
        (("云雾白", 2900),),
    ),
    ProductSpec(
        "wc-15w",
        "速派 WC15 无线充电器",
        "速派",
        "无线充电器",
        "15W 无线快充，带散热风扇，支持异物检测。",
        {"power_w": 15, "protocol": "Qi", "warranty_months": 12},
        (("曜石黑", 11900), ("云雾白", 11900)),
    ),
    # ---- 鞋服箱包 -------------------------------------------------------
    ProductSpec(
        "qf-rf1",
        "轻风 疾风 RF-1 缓震跑鞋",
        "轻风",
        "跑步鞋",
        "高回弹中底配合透气网面，日常慢跑与通勤跑步都合适，单只约 245 克。",
        {
            "closure": "系带",
            "drop_mm": 8,
            "weight_g": 245,
            "upper": "飞织网面",
            "warranty_months": 3,
        },
        (("碳黑 42", 69900), ("碳黑 43", 69900), ("云白 42", 69900)),
    ),
    ProductSpec(
        "qf-rf2",
        "轻风 云逐 RF-2 轻量跑鞋",
        "轻风",
        "跑步鞋",
        "轻量训练跑鞋，鞋面更薄，适合夏季跑步和健身房有氧。",
        {"closure": "系带", "drop_mm": 6, "weight_g": 210, "upper": "单层网布"},
        (("雾蓝 41", 49900), ("雾蓝 42", 49900), ("碳黑 42", 49900)),
    ),
    ProductSpec(
        "qf-cs1",
        "轻风 城市漫步 CS-1 休闲运动鞋",
        "轻风",
        "运动鞋",
        "百搭小白鞋，软弹鞋垫，适合日常通勤与周末逛街。",
        {"closure": "系带", "weight_g": 280, "upper": "合成革", "warranty_months": 3},
        (("米白 41", 39900), ("米白 42", 39900), ("碳黑 42", 39900)),
    ),
    ProductSpec(
        "mx-tee01",
        "棉序 重磅纯棉短袖 T 恤",
        "棉序",
        "T恤",
        "260g 重磅纯棉，领口不易变形，宽松直筒版型。",
        {"material": "100% 棉", "weight_g": 260, "fit": "宽松", "season": "夏季"},
        (("白色 M", 8900), ("白色 L", 8900), ("黑色 L", 8900), ("黑色 XL", 8900)),
    ),
    ProductSpec(
        "mx-hood01",
        "棉序 加绒连帽卫衣",
        "棉序",
        "卫衣",
        "内里加绒，落肩版型，秋冬单穿或叠穿都合适。",
        {"material": "棉混纺", "fleece": True, "fit": "落肩宽松", "season": "秋冬"},
        (("燕麦色 M", 19900), ("燕麦色 L", 19900), ("雾灰色 L", 19900)),
    ),
    ProductSpec(
        "xl-bag20",
        "行旅 通勤双肩包 20L",
        "行旅",
        "双肩包",
        "20L 容量，独立 16 寸电脑仓，防泼水面料，适合通勤与短途出差。",
        {"capacity_l": 20, "laptop_inch": 16, "waterproof": True, "weight_g": 780},
        (("深空灰", 25900), ("曜石黑", 25900)),
    ),
    ProductSpec(
        "xl-case20",
        "行旅 20 寸登机行李箱",
        "行旅",
        "行李箱",
        "万向静音轮与 TSA 密码锁，20 寸可直接登机。",
        {"size_inch": 20, "material": "PC+ABS", "lock": "TSA 密码锁", "weight_kg": 3.2},
        (("象牙白", 39900), ("深空灰", 39900)),
    ),
    # ---- 家居生活 -------------------------------------------------------
    ProductSpec(
        "nj-cup500",
        "暖居 316 不锈钢保温杯 500ml",
        "暖居",
        "保温杯",
        "316 不锈钢内胆，保温 12 小时，杯盖可拆卸清洗。",
        {"capacity_ml": 500, "material": "316 不锈钢", "keep_warm_hours": 12},
        (("雾银", 12900), ("松石绿", 12900), ("曜石黑", 12900)),
    ),
    ProductSpec(
        "nj-box3",
        "暖居 玻璃保鲜盒三件套",
        "暖居",
        "保鲜盒",
        "耐热玻璃盒身，可微波加热，三档容量组合适合备餐。",
        {"material": "耐热玻璃", "pieces": 3, "microwave_safe": True},
        (("透明", 9900),),
    ),
    ProductSpec(
        "nj-pillow",
        "暖居 记忆棉护颈枕",
        "暖居",
        "枕头",
        "慢回弹记忆棉，中间低两侧高的护颈曲线，适合侧睡人群。",
        {"material": "记忆棉", "height_cm": 10, "firmness": "中等"},
        (("标准款", 15900),),
    ),
    ProductSpec(
        "cx-bed4",
        "晨曦 全棉四件套 1.8m",
        "晨曦",
        "床品四件套",
        "60 支长绒棉，亲肤透气，含被套一件、床单一件、枕套两只。",
        {"material": "60 支长绒棉", "size": "1.8m 床", "pieces": 4},
        (("雾灰", 39900), ("奶油白", 39900)),
    ),
    ProductSpec(
        "cx-towel",
        "晨曦 抗菌浴巾",
        "晨曦",
        "浴巾",
        "长绒棉加厚毛圈，吸水快，抗菌整理工艺。",
        {"material": "长绒棉", "size_cm": "70x140", "gsm": 480},
        (("奶白", 6900), ("雾灰", 6900)),
    ),
    ProductSpec(
        "my-lamp1",
        "木言 护眼台灯 L1",
        "木言",
        "台灯",
        "无频闪国 AA 级照度，五档色温，适合长时间阅读与办公。",
        {"illuminance": "国 AA 级", "color_temp": "3000-5500K", "usb_charging": True},
        (("象牙白", 19900),),
    ),
    ProductSpec(
        "my-table",
        "木言 实木收纳边几",
        "木言",
        "边几",
        "橡胶木框架，带抽屉收纳，沙发边与床头都能放。",
        {"material": "橡胶木", "size_cm": "40x40x55", "drawer": True},
        (("原木色", 29900),),
    ),
    # ---- 厨房小电 -------------------------------------------------------
    ProductSpec(
        "yh-af4l",
        "焰火 AF-4L 空气炸锅",
        "焰火",
        "空气炸锅",
        "4L 容量，可视窗口，八种预设菜单，无需预热。",
        {"capacity_l": 4, "power_w": 1400, "preset_count": 8, "warranty_months": 12},
        (("奶油白", 39900), ("曜石黑", 39900)),
    ),
    ProductSpec(
        "yh-cm1",
        "焰火 胶囊咖啡机 CM-1",
        "焰火",
        "咖啡机",
        "19bar 萃取压力，30 秒出杯，兼容主流胶囊。",
        {"pressure_bar": 19, "water_tank_ml": 600, "warranty_months": 12},
        (("奶油白", 59900),),
    ),
    ProductSpec(
        "yh-w3",
        "焰火 即热饮水机 W3",
        "焰火",
        "饮水机",
        "3 秒即热，六档水温，2L 水箱适合桌面使用。",
        {"tank_ml": 2000, "power_w": 2200, "temp_levels": 6, "warranty_months": 12},
        (("象牙白", 49900),),
    ),
    ProductSpec(
        "yh-bl2",
        "焰火 破壁料理机 BL-2",
        "焰火",
        "料理机",
        "1.75L 冷热双打，可做豆浆、米糊与果蔬汁，带隔音罩。",
        {"capacity_l": 1.75, "power_w": 1200, "heat": True, "warranty_months": 24},
        (("曜石黑", 69900),),
    ),
    # ---- 个护美妆 -------------------------------------------------------
    ProductSpec(
        "qy-tb3",
        "清野 声波电动牙刷 T3",
        "清野",
        "电动牙刷",
        "每分钟 38000 次声波震动，三种清洁模式，续航 30 天。",
        {"vibration_per_min": 38000, "modes": 3, "battery_days": 30, "waterproof": "IPX7"},
        (("月光白", 19900), ("雾蓝", 19900)),
        False,
    ),
    ProductSpec(
        "qy-hd2",
        "清野 负离子吹风机 HD-2",
        "清野",
        "吹风机",
        "高速马达配合负离子护发，五档风温，机身约 420 克。",
        {"power_w": 1600, "ion": True, "weight_g": 420, "warranty_months": 24},
        (("月光白", 29900), ("雾蓝", 29900)),
    ),
    ProductSpec(
        "qy-sh500",
        "清野 氨基酸洗发水 500ml",
        "清野",
        "洗发水",
        "氨基酸表活，温和清洁，适合日常使用。",
        {"capacity_ml": 500, "hair_type": "通用", "sulfate_free": True},
        (("500ml", 8900),),
        False,
    ),
    ProductSpec(
        "qy-mask10",
        "清野 玻尿酸补水面膜 10 片",
        "清野",
        "面膜",
        "玻尿酸与泛醇复配，单片 25ml 精华，贴合度高。",
        {"pieces": 10, "volume_ml": 25, "skin_type": "干性/中性"},
        (("10 片装", 9900),),
        False,
    ),
    ProductSpec(
        "qy-hand",
        "清野 烟酰胺护手霜",
        "清野",
        "护手霜",
        "烟酰胺配合乳木果油，滋润不黏腻，随身装 50ml。",
        {"capacity_ml": 50, "ingredient": "烟酰胺"},
        (("50ml", 3900),),
        False,
    ),
    # ---- 运动户外 -------------------------------------------------------
    ProductSpec(
        "qf-yoga",
        "轻风 加厚防滑瑜伽垫",
        "轻风",
        "瑜伽垫",
        "8mm 加厚 TPE 材质，双面防滑纹路，附收纳带。",
        {"thickness_mm": 8, "material": "TPE", "size_cm": "183x61"},
        (("雾紫", 12900), ("松石绿", 12900)),
    ),
    ProductSpec(
        "qf-dumbbell",
        "轻风 可调节哑铃 10kg",
        "轻风",
        "哑铃",
        "一对可调节哑铃，快速换片，适合居家力量训练。",
        {"weight_kg": 10, "adjustable": True, "material": "包胶铸铁"},
        (("曜石黑", 29900),),
    ),
    ProductSpec(
        "qf-hike40",
        "轻风 户外登山包 40L",
        "轻风",
        "登山包",
        "40L 容量，背负透气系统，附防雨罩，适合两天徒步。",
        {"capacity_l": 40, "rain_cover": True, "weight_g": 1250},
        (("松石绿", 45900), ("碳黑", 45900)),
    ),
    # ---- 宠物 -----------------------------------------------------------
    ProductSpec(
        "md-cat2",
        "喵岛 全价成猫粮 2kg",
        "喵岛",
        "猫粮",
        "鲜鸡肉配方，粗蛋白 38%，适合一岁以上成猫。",
        {"weight_kg": 2, "protein_pct": 38, "flavor": "鸡肉"},
        (("2kg", 12900),),
        False,
    ),
    ProductSpec(
        "md-litter",
        "喵岛 豆腐猫砂 6L",
        "喵岛",
        "猫砂",
        "植物豆腐砂，结团快、粉尘低，可冲厕所。",
        {"volume_l": 6, "material": "豆腐砂", "flushable": True},
        (("原味", 3900), ("绿茶味", 3900)),
        False,
    ),
    # ---- 食品 -----------------------------------------------------------
    ProductSpec(
        "sy-coffee",
        "食野 精品挂耳咖啡 20 包",
        "食野",
        "咖啡",
        "中深烘焙拼配豆，现磨挂耳，每包 10g。",
        {"pieces": 20, "weight_g": 200, "roast": "中深烘焙"},
        (("20 包", 6900),),
        False,
    ),
    ProductSpec(
        "sy-nuts",
        "食野 每日坚果礼盒 30 包",
        "食野",
        "坚果",
        "七种坚果果干独立小包，每包 25g，适合办公室加餐。",
        {"pieces": 30, "weight_g": 750, "flavor": "原味"},
        (("30 包", 12900),),
        False,
    ),
    # ---- 数码新增 -------------------------------------------------------
    ProductSpec(
        "gm-mon27",
        "光影 27 英寸 2K 显示器",
        "光影",
        "显示器",
        "2K 分辨率 IPS 面板，75Hz 刷新率，支持 Type-C 65W 反向供电。",
        {"size_inch": 27, "resolution": "2560x1440", "refresh_hz": 75, "type_c_w": 65},
        (("曜石黑", 129900),),
    ),
    ProductSpec(
        "yq-band3",
        "云栖 智能手环 Band 3",
        "云栖",
        "智能手环",
        "1.6 英寸 AMOLED 屏，心率与血氧监测，续航 14 天。",
        {"screen_inch": 1.6, "battery_days": 14, "waterproof": "5ATM", "warranty_months": 12},
        (("曜石黑", 24900), ("雾银白", 24900)),
    ),
)

PROMOTIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "autumn-threshold",
        "name": "秋季满 300 减 40",
        "rule": {"type": "threshold_discount", "threshold_cents": 30000, "discount_cents": 4000},
        "starts_at": datetime(2026, 9, 15, tzinfo=UTC),
        "ends_at": datetime(2026, 11, 15, 15, 59, tzinfo=UTC),
        "status": "active",
    },
    {
        "key": "headphone-10off",
        "name": "耳机品类九折",
        "rule": {"type": "category_discount", "category": "降噪耳机", "discount_bps": 9000},
        "starts_at": datetime(2026, 10, 1, tzinfo=UTC),
        "ends_at": datetime(2026, 11, 1, 15, 59, tzinfo=UTC),
        "status": "active",
    },
    {
        "key": "newcomer-coupon",
        "name": "新客立减 20 元",
        "rule": {"type": "flat_discount", "discount_cents": 2000, "first_order_only": True},
        "starts_at": datetime(2026, 10, 1, tzinfo=UTC),
        "ends_at": datetime(2026, 12, 31, 15, 59, tzinfo=UTC),
        "status": "active",
    },
    {
        "key": "summer-sale",
        "name": "夏季特惠（已结束）",
        "rule": {"type": "flat_discount", "discount_cents": 5000},
        "starts_at": datetime(2026, 6, 1, tzinfo=UTC),
        "ends_at": datetime(2026, 8, 31, 15, 59, tzinfo=UTC),
        "status": "ended",
    },
)

ORDER_STATUS_PLAN: tuple[str, ...] = (
    ["created"] * 8
    + ["paid"] * 10
    + ["processing"] * 10
    + ["shipped"] * 15
    + ["delivered"] * 30
    + ["completed"] * 20
    + ["cancelled"] * 7
)

SHOPPER_NAMES: tuple[str, ...] = (
    "用户A01",
    "用户A02",
    "用户A03",
    "用户A04",
    "用户A05",
    "用户A06",
    "用户A07",
    "用户A08",
    "用户A09",
    "用户A10",
    "用户A11",
    "用户A12",
)


@dataclass(slots=True)
class Dataset:
    """All synthetic rows, grouped by table."""

    shop: dict[str, Any]
    users: list[dict[str, Any]] = field(default_factory=list)
    products: list[dict[str, Any]] = field(default_factory=list)
    variants: list[dict[str, Any]] = field(default_factory=list)
    inventory: list[dict[str, Any]] = field(default_factory=list)
    promotions: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)
    order_items: list[dict[str, Any]] = field(default_factory=list)
    shipments: list[dict[str, Any]] = field(default_factory=list)
    shipment_events: list[dict[str, Any]] = field(default_factory=list)


def shop_id() -> UUID:
    return stable_uuid("shop", "demo")


def masked_address(index: int) -> str:
    """Return a synthetic, masked address that cannot identify a real person."""
    districts = ("浦东新区", "朝阳区", "南山区", "武侯区", "西湖区")
    return f"上海市 {districts[index % len(districts)]} 示例路 ** 号（合成地址）"


def masked_tracking(index: int) -> str:
    return f"SF{1000 + index % 9000}****{index:04d}"


def build_dataset() -> Dataset:
    """Build the whole synthetic dataset deterministically."""
    rng = random.Random(SEED)
    shop_uuid = shop_id()
    dataset = Dataset(
        shop={
            "id": shop_uuid,
            "name": SHOP_NAME,
            "locale": "zh-CN",
            "currency": CURRENCY,
            "timezone": "Asia/Shanghai",
        }
    )

    for index, masked_name in enumerate(SHOPPER_NAMES, start=1):
        dataset.users.append(
            {
                "id": stable_uuid("user", "shopper", f"{index:02d}"),
                "shop_id": shop_uuid,
                "email_ci": f"shopper{index:02d}@example.invalid",
                "password_hash": "!synthetic-account-no-login",
                "role": "shopper",
                "display_name_masked": masked_name,
                "is_active": True,
            }
        )
    dataset.users.append(
        {
            "id": stable_uuid("user", "support", "01"),
            "shop_id": shop_uuid,
            "email_ci": "support01@example.invalid",
            "password_hash": "!synthetic-account-no-login",
            "role": "support",
            "display_name_masked": "客服B01",
            "is_active": True,
        }
    )
    dataset.users.append(
        {
            "id": stable_uuid("user", "admin", "01"),
            "shop_id": shop_uuid,
            "email_ci": "admin01@example.invalid",
            "password_hash": "!synthetic-account-no-login",
            "role": "admin",
            "display_name_masked": "管理员C01",
            "is_active": True,
        }
    )

    variant_records: list[dict[str, Any]] = []
    for spec in PRODUCTS:
        product_uuid = stable_uuid("product", spec.slug)
        dataset.products.append(
            {
                "id": product_uuid,
                "shop_id": shop_uuid,
                "title": spec.title,
                "description": spec.description,
                "brand": spec.brand,
                "category": spec.category,
                "attributes_jsonb": spec.attributes,
                "status": "active",
                "is_synthetic": True,
            }
        )
        for offset, (color, price_cents) in enumerate(spec.variants, start=1):
            sku = f"SM-{spec.slug.upper()}-{offset:02d}"
            variant_uuid = stable_uuid("variant", sku)
            variant_records.append(
                {
                    "id": variant_uuid,
                    "shop_id": shop_uuid,
                    "product_id": product_uuid,
                    "sku": sku,
                    "title": f"{spec.title} · {color}",
                    "attributes_jsonb": {"color": color},
                    "price_cents": price_cents,
                    "currency": CURRENCY,
                    "status": "active",
                    "product_slug": spec.slug,
                    "product_category": spec.category,
                    "product_title": spec.title,
                    "returnable": spec.returnable,
                }
            )
    dataset.variants = variant_records

    for index, variant in enumerate(variant_records):
        available = 0 if index % 9 == 4 else rng.choice((3, 8, 12, 25, 40, 60, 120))
        dataset.inventory.append(
            {
                "id": stable_uuid("inventory", variant["sku"], WAREHOUSE),
                "shop_id": shop_uuid,
                "variant_id": variant["id"],
                "warehouse_code": WAREHOUSE,
                "available_qty": available,
                "reserved_qty": rng.choice((0, 0, 0, 1, 2)),
                "source_system": "mock_oms",
            }
        )

    for promotion in PROMOTIONS:
        dataset.promotions.append(
            {
                "id": stable_uuid("promotion", promotion["key"]),
                "shop_id": shop_uuid,
                "name": promotion["name"],
                "rule_jsonb": promotion["rule"],
                "starts_at": promotion["starts_at"],
                "ends_at": promotion["ends_at"],
                "status": promotion["status"],
                "is_synthetic": True,
            }
        )

    shoppers = [user for user in dataset.users if user["role"] == "shopper"]
    statuses = list(ORDER_STATUS_PLAN)
    rng.shuffle(statuses)

    for index in range(1, 101):
        status = statuses[index - 1]
        placed_at = ANCHOR - timedelta(days=rng.randint(1, 120), hours=rng.randint(0, 20))
        if status == "delivered" and index % 11 == 0:
            placed_at = ANCHOR - timedelta(days=2, hours=3)
        elif status == "delivered" and index % 13 == 0:
            placed_at = ANCHOR - timedelta(days=6, hours=5)

        delivered_at: datetime | None = None
        cancelled_at: datetime | None = None
        if status in {"delivered", "completed"}:
            delivered_at = min(placed_at + timedelta(days=rng.randint(2, 6)), ANCHOR)
        if status == "cancelled":
            cancelled_at = placed_at + timedelta(hours=rng.randint(1, 48))

        item_count = rng.choice((1, 1, 1, 2, 2, 3))
        chosen = rng.sample(variant_records, item_count)
        order_uuid = stable_uuid("order", f"SM-2026-{index:05d}")
        item_rows: list[dict[str, Any]] = []
        total_cents = 0
        for line_no, variant in enumerate(chosen, start=1):
            quantity = rng.choice((1, 1, 1, 2))
            unit_price = variant["price_cents"]
            line_total = unit_price * quantity
            total_cents += line_total
            item_rows.append(
                {
                    "id": stable_uuid("order_item", str(order_uuid), str(line_no)),
                    "shop_id": shop_uuid,
                    "order_id": order_uuid,
                    "variant_id": variant["id"],
                    "sku_snapshot": variant["sku"],
                    "title_snapshot": variant["title"],
                    "category_snapshot": variant["product_category"],
                    "is_returnable_snapshot": variant["returnable"],
                    "quantity": quantity,
                    "unit_price_cents": unit_price,
                    "line_total_cents": line_total,
                    "status": "cancelled" if status == "cancelled" else "active",
                    "delivered_at": delivered_at,
                }
            )
        dataset.order_items.extend(item_rows)
        dataset.orders.append(
            {
                "id": order_uuid,
                "shop_id": shop_uuid,
                "user_id": shoppers[(index - 1) % len(shoppers)]["id"],
                "order_no": f"SM-2026-{index:05d}",
                "status": status,
                "total_cents": total_cents,
                "currency": CURRENCY,
                "placed_at": placed_at,
                "delivered_at": delivered_at,
                "cancelled_at": cancelled_at,
                "shipping_address_masked": masked_address(index),
                "source_system": "mock_oms",
                "is_synthetic": True,
            }
        )

        if status in {"shipped", "delivered", "completed"}:
            shipment_uuid = stable_uuid("shipment", str(order_uuid))
            shipped_at = placed_at + timedelta(hours=rng.randint(6, 30))
            dataset.shipments.append(
                {
                    "id": shipment_uuid,
                    "shop_id": shop_uuid,
                    "order_id": order_uuid,
                    "carrier": "顺捷速运（合成）",
                    "tracking_no_masked": masked_tracking(index),
                    "tracking_no_hash": stable_uuid("tracking", str(index)).bytes,
                    "status": "delivered" if delivered_at else "in_transit",
                    "shipped_at": shipped_at,
                    "estimated_delivery_at": shipped_at + timedelta(days=3),
                    "delivered_at": delivered_at,
                    "source_system": "mock_oms",
                }
            )
            timeline: list[tuple[str, str, datetime]] = [
                ("picked_up", "快件已由仓库揽收", shipped_at),
                ("in_transit", "快件已到达转运中心", shipped_at + timedelta(hours=8)),
            ]
            if delivered_at:
                timeline.append(
                    ("out_for_delivery", "快件正在派送中", delivered_at - timedelta(hours=4))
                )
                timeline.append(("delivered", "快件已签收", delivered_at))
            for sequence, (event_status, description, occurred_at) in enumerate(timeline, start=1):
                dataset.shipment_events.append(
                    {
                        "id": stable_uuid("shipment_event", str(shipment_uuid), str(sequence)),
                        "shop_id": shop_uuid,
                        "shipment_id": shipment_uuid,
                        "sequence_no": sequence,
                        "status": event_status,
                        "description": description,
                        "occurred_at": occurred_at,
                    }
                )

    return dataset
