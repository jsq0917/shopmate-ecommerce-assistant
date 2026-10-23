"""Stage-17 corpus expansion — digital (数码) category documents.

Four synthetic policy documents, authored once as parameterised builders and
instantiated twice: a superseded version and a current version that differ on
the numbers retrieval must respect (activation rule for no-reason returns,
battery warranty 6 vs 12 months, accessory warranty 3 vs 6 months,
price-protection 3 vs 7 days, data-backup window 3 vs 7 days).

All content is written for this project; no real merchant, brand or regulation
is described.
"""

from __future__ import annotations

from shopmate_ecommerce_assistant.synthetic.corpus_types import KB_CN, PolicyDoc, Section, _doc

_OLD_FROM = "2026-08-01T00:00:00Z"
_TO = "2026-10-01T00:00:00Z"
_NEW_FROM = "2026-10-01T00:00:00Z"


# ============================================================ 附录生成器
# The annexes carry the bulk of the corpus volume and, more importantly, the
# version-sensitive numbers: the same question is answered differently by the
# 2024 / 2025 / 2026.08 / 2026.10 versions, which is what makes version
# filtering observable in retrieval instead of a pure similarity exercise.
def _digital_return_annex(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "附录：数码退换情形速查",
            (
                "情形一：签收第二日开机联网并登录账号后申请无理由退货。结论：激活判定以首次开机联网、登录账号或完成系统绑定为准，按当前激活规则处理。",
                "情形二：仅开机未联网、未登录账号。结论：视为未激活，可按未激活商品申请无理由退货。",
                "情形三：已退出账号但未恢复出厂设置。结论：数据未清除会影响二次销售判定，建议先完成清除再寄回。",
                "情形四：到货即屏幕碎裂。结论：属于到货即损坏，七日内可退换，运费由商城承担。",
                "情形五：签收第九日发现无法充电。结论：超出七日无理由窗口，按性能故障与保修流程处理。",
                "情形六：退货时缺少数据线。结论：缺少配件按标价扣减，原始包装缺失会影响二次销售判定。",
                "情形七：一次性封贴破损但设备未使用。结论：需经售后判定是否影响二次销售。",
                "情形八：分期订单申请退货。结论：验收通过后优先冲抵未出账分期。",
                "情形九：忘记退出账号就寄回。结论：售后按当前激活与数据清除规则处理，建议寄回前退出全部账号。",
                "情形十：屏幕两个亮点分布在不同区域。结论：视为正常显示差异，不按显示质量问题处理。",
                "情形十一：签收当日外包装破损。结论：当场拍照并联系售后，可按到货即损坏处理。",
                "情形十二：换货审核期间改主意想改为退货。结论：审核通过前可联系售后变更处理方式。",
                "情形十三：已激活设备外观有划痕。结论：外观问题按售后规则判定，激活不影响质量问题的处理。",
                "情形十四：超过七日窗口的性能故障。结论：按保修政策处理，需提供故障照片、视频或检测结论。",
                "情形十五：定制刻字配件能无理由退吗。结论：个人化定制不适用无理由退换。",
                "情形十六：错发的数码商品。结论：不受激活与窗口限制，按错发规则处理，运费由商城承担。",
            ),
        ),
        Section(
            "附录：数码退换深度问答",
            (
                "问题一：当前版本的激活退货规则是什么？答复：见激活与退货章节的当前规则。",
                "问题二：退货申请的审核时效是多久？答复：一个工作日内给出审核结论。",
                f"问题三：数据清除报告由谁出具？答复：{n['wipe_report'] or '按验收流程记录，当前版本未单独出具报告。'}",
                f"问题四：哪些订单明确不支持无理由退换？答复：{n['not_returnable']}",
                "问题五：退货物流可以寄到付吗？答复：不支持，需按售后提供的地址寄回并保留单号。",
                "问题六：检测会导致数据丢失吗？答复：检测过程可能恢复出厂设置，需提前完成备份。",
                "问题七：拒收和退货的区别是什么？答复：拒收在签收前提出，退货在签收后申请。",
                "问题八：无理由退货的运费谁承担？答复：寄回运费由消费者承担，质量问题由商城承担往返运费。",
                "问题九：保价寄回的费用在承担范围内吗？答复：不在，保价费用需消费者自行承担。",
                "问题十：换货发出后可以改地址吗？答复：物流发出前可联系售后修改，发出后以物流转寄为准。",
                "问题十一：换货完成后原订单还能退吗？答复：不能，换货完成后原订单不可再申请退货。",
                "问题十二：退货窗口从哪天起算？答复：自实际签收之日起计算。",
                "问题十三：物流单号填错怎么办？答复：在售后入口更新物流信息，超时未更新的申请可能关闭。",
                "问题十四：拒收的订单怎么退款？答复：仓库登记拒收，验收通过后按原渠道退款。",
                "问题十五：退货后被扣款怎么查询？答复：退款明细列示配件扣减与运费项，可在订单页查看。",
                "问题十六：发票需要随机器寄回吗？答复：电子发票无需退回，纸质发票按售后指引处理。",
                "问题十七：激活规则有争议时怎么处理？答复：提交开机记录与截图申请复核，复核由售后人工完成。",
                "问题十八：已激活商品的质量问题退换货运费谁承担？答复：质量问题退换货的往返运费由商城承担。",
                "问题十九：可以只退订单中的部分商品吗？答复：按订单与配件完整性判定，缺少配件按标价扣减。",
                "问题二十：上门取件覆盖数码商品吗？答复：按通用退货政策的取件方式执行。",
            ),
        ),
        Section(
            "附录：数码退换规则边界与例外",
            (
                "边界一：激活判定以系统记录的开机联网、登录账号或绑定行为为准，不凭消费者自述。",
                "边界二：无理由退货运费由消费者承担寄回段，质量问题退换货的往返运费由商城承担。",
                "边界三：缺少随附配件按标价扣减，原始包装与封贴缺失影响二次销售判定。",
                "边界四：个人化定制刻字配件不适用无理由退换。",
                "边界五：错发商品不受激活与窗口限制，运费由商城承担。",
                "边界六：退货审核通过前可申请变更处理方式，通过后不可再改为退货。",
                "边界七：退换窗口自实际签收之日起计算，以物流签收记录为准。",
                "边界八：屏幕亮点数量与分布按显示质量标准判定，集中分布超出标准按质量问题处理。",
                "边界九：分期订单退货时验收通过的款项优先冲抵未出账分期。",
                "边界十：退换规则以生效日期对应的版本为准。",
            ),
        ),
    )


def _digital_warranty_annex(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "附录：数码保修情形速查",
            (
                f"情形一：主机签收第十个月无法开机。结论：非人为性能故障，在 {n['main_months']} 个月主机保修期内可申请保修。",
                f"情形二：电池使用八个月最大容量降至标称值七成五。结论：低于百分之八十，可申请{n['battery_action']}。",
                f"情形三：屏幕签收第五个月出现四个亮点且集中在一角。结论：超出亮点标准，按显示质量问题处理，屏幕保修 {n['screen_months']} 个月。",
                f"情形四：数据线三个月接触不良。结论：随附配件保修 {n['accessory_months']} 个月内可申请。",
                "情形五：进水后无法充电。结论：进液不在保修范围内，可咨询付费维修。",
                "情形六：私拆后盖后无法开机。结论：私自拆机不在保修范围内。",
                "情形七：保修期内寄修运费谁出。结论：保修范围内的寄修运费由商城承担。",
                "情形八：换货商品保修怎么算。结论：沿用原订单的保修截止日期。",
                "情形九：二手购买的数码能保修吗。结论：保修不随二手转让转移。",
                f"情形十：屏幕保修期与主机一致吗。结论：不一致，屏幕为 {n['screen_months']} 个月，主机为 {n['main_months']} 个月。",
                "情形十一：电池循环损耗能保修吗。结论：属于正常老化，不在保修范围内。",
                "情形十二：无法提供发票只有订单号。结论：订单号或发票均可作为购买凭证，按支付记录判定。",
                f"情形十三：保修检测周期多久。结论：{n['detect_days']}。",
                "情形十四：配件丢失能补购并单独保修吗。结论：配件丢失需重新购买。",
                "情形十五：跌落导致的外壳破损。结论：人为损坏不在保修范围内，可付费维修。",
                "情形十六：蓝牙耳机异常断连。结论：非人为的异常断连在保修范围内。",
            ),
        ),
        Section(
            "附录：数码保修深度问答",
            (
                "问题一：保修申请提交后多久受理？答复：一个工作日内给出受理结论。",
                "问题二：保修期内可以付费加速处理吗？答复：可以，维修前会给出报价。",
                "问题三：屏幕维修和换新怎么选？答复：无法维修时可申请换新，以检测结论为准。",
                "问题四：配件可以单独购买吗？答复：可以，随附配件按商城配件页价格购买。",
                "问题五：多次故障能反复保修吗？答复：同一故障修复后不重复保修，新故障可再次申请。",
                "问题六：保修期从哪天起算？答复：自签收之日起计算。",
                "问题七：保修范围包括哪些故障？答复：无法开机、无法充电、触控失灵与异常断连等非人为性能故障。",
                "问题八：人为损坏可以付费维修吗？答复：可以，维修前给出报价，确认后开始维修。",
                "问题九：保修需要寄回原包装吗？答复：不需要，但需做好运输防护。",
                "问题十：寄修前要做什么？答复：备份并清除个人数据，退出全部账号。",
                "问题十一：送修方式有哪几种？答复：寄修与指定服务点检测两种。",
                "问题十二：维修更换的配件保修多久？答复：按维修报价单约定，整机保修仍按原订单计算。",
                "问题十三：同一故障修复后又出现能再保修吗？答复：同一故障不重复保修，新的故障可再次申请。",
                "问题十四：屏幕出现亮线能保修吗？答复：非人为的显示故障在屏幕保修期内可申请。",
                "问题十五：保修能延长吗？答复：保修不延长原保修期，更换部件沿用原订单截止日期。",
                "问题十六：跨境订单能保修吗？答复：以订单购买地区对应的保修政策为准。",
                "问题十七：复检结论不一致怎么办？答复：可申请复核，复核结论以工单记录为准。",
                "问题十八：保修期内可以退货吗？答复：在退换窗口内符合条件可退换，超窗口按保修处理。",
                "问题十九：付费维修会先报价吗？答复：会，维修前给出报价，消费者确认后才开始维修。",
                "问题二十：配件保修与主机保修冲突时怎么判？答复：按各自保修期分别判定。",
            ),
        ),
        Section(
            "附录：数码保修规则边界与例外",
            (
                "边界一：保修范围仅覆盖非人为性能故障，进液与私自拆机不在保修范围内。",
                "边界二：人为损坏如跌落、挤压与外壳破损不在保修范围内，可付费维修。",
                "边界三：电池最大容量降至标称值八成以下且循环正常时按当前版本规则处理。",
                "边界四：保修不随二手转让转移，以原订单购买者与购买凭证为准。",
                "边界五：保修期自签收之日起计算，换货商品沿用原订单保修截止日期。",
                "边界六：同一故障修复后不重复保修，修复后出现的新故障可再次申请。",
                "边界七：保修期内的寄修运费由商城承担，保价费用由消费者承担。",
                "边界八：订单号或发票均可作为购买凭证，按支付记录判定保修资格。",
                "边界九：跨境订单以购买地区对应的保修政策为准。",
                "边界十：保修规则以生效日期对应的版本为准。",
            ),
        ),
    )


def _digital_invoice_annex(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "附录：数码价保情形速查",
            (
                f"情形一：数码商品支付后第四日同款降价。结论：在 {n['pp_days']} 日价保期内可申请价格保护。",
                "情形二：使用优惠券后的价差。结论：优惠券产生的价差不在价保范围内。",
                "情形三：订单已退货还能价保吗。结论：申请价保的订单不得已退货或已取消。",
                "情形四：不同配置可以比价吗。结论：需同款同配置同颜色。",
                f"情形五：价保差额怎么返。结论：以{n['pp_refund']}方式返还，优惠券有效期三十天。",
                "情形六：同一商品能多次拿到价保补偿吗。结论：次数不限，但同一商品仅补偿一次。",
                f"情形七：订单完成第四十五天想补开发票。结论：{n['invoice_days']} 日内可申请补开，超期需人工评估。",
                "情形八：价保比价含运费吗。结论：不含运费与增值服务。",
                "情形九：秒杀价能价保吗。结论：限时秒杀产生的价差不在价保范围内。",
                "情形十：激活商品的发票信息以什么为准。结论：以订单支付记录为准。",
                "情形十一：补开发票要什么材料。结论：订单号与开票信息。",
                "情形十二：价保申请多久出结论。结论：系统自动比价后在一个工作日内给出结论。",
                "情形十三：部分退款后还能价保吗。结论：订单未取消且在价保期内可申请。",
                "情形十四：价保比价要同店铺吗。结论：需同一店铺同一商品同一配置。",
            ),
        ),
        Section(
            "附录：数码价保深度问答",
            (
                "问题一：价保申请提交后多久出结论？答复：系统自动比价后在一个工作日内给出结论。",
                "问题二：价保补偿可以提现吗？答复：按当前版本的返还方式执行，优惠券形式不可提现。",
                "问题三：价保比价要同店铺吗？答复：需同一店铺同一商品同一配置。",
                "问题四：多件商品能合并价保吗？答复：按订单内商品分别比价，分别补偿。",
                "问题五：部分退款后还能价保吗？答复：订单未取消且在价保期内可申请。",
                "问题六：价保申请能撤销吗？答复：结论出具前可撤销，重新提交需在价保期内。",
                "问题七：跨年度发票红冲怎么处理？答复：由财务在申报期内按税务要求处理。",
                "问题八：价保比价含赠品价值吗？答复：不含赠品与增值服务。",
                "问题九：价保补偿的券能叠加使用吗？答复：按优惠券使用规则执行。",
                "问题十：订单取消后已开的发票怎么办？答复：需先红冲原发票，再按实际金额处理。",
                "问题十一：补开的发票抬头可以改吗？答复：开票当月可申请换开，跨月需先红冲再重开。",
                "问题十二：价保申请多久出结论？答复：一个工作日内。",
                "问题十三：跨月订单能补票吗？答复：在补开期限内可申请，超期人工评估。",
                "问题十四：电子发票多久开出？答复：参照通用开票规则的时效。",
                "问题十五：价保和退换货能同时进行吗？答复：可以，分别计算。",
                "问题十六：专用发票能补开吗？答复：可申请，需提交企业资质并经审核。",
                "问题十七：价保失败能申诉吗？答复：可提交页面截图申请复核。",
                "问题十八：多件商品能合并申请价保吗？答复：按订单内商品分别比价，分别补偿。",
            ),
        ),
        Section(
            "附录：数码价保规则边界与例外",
            (
                "边界一：价保比价需同一店铺、同一商品、同一配置与同一颜色。",
                "边界二：优惠券、秒杀与限时活动产生的价差不在价保范围内。",
                "边界三：价保比价不含运费、赠品与增值服务。",
                "边界四：申请价保的订单不得已退货或已取消。",
                "边界五：同一商品同一订单仅补偿一次价差，次数不限指不同商品。",
                "边界六：价保差额按当前版本约定的返还方式退回，券形式不可提现。",
                "边界七：补开发票需在补开期限内申请，超期由人工评估。",
                "边界八：电子发票信息以订单支付记录为准，换开需先红冲原发票。",
                "边界九：专用发票补开需提交企业资质并经审核。",
                "边界十：价保与发票规则以生效日期对应的版本为准。",
            ),
        ),
    )


def _digital_backup_annex(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "附录：数据备份情形速查",
            (
                f"情形一：送修申请已提交，多久内要完成备份？结论：{n['backup_days']}内完成数据备份与清除。",
                "情形二：超过备份窗口未处理。结论：售后按流程推进检测，数据丢失风险由消费者承担。",
                f"情形三：换货后怎么迁移数据。结论：{n['migration_help']}",
                "情形四：忘记退出账号就寄回。结论：售后在检测前按规则代为恢复出厂设置。",
                "情形五：哪些数据最容易漏备份。结论：聊天记录、照片与令牌类应用。",
                "情形六：外部存储能作为备份介质吗。结论：可以，建议同时保留两份。",
                "情形七：售后人员会查看设备数据吗。结论：按最小必要原则操作，全程留痕。",
                f"情形八：数据清除报告有什么用。结论：{n['wipe_report'] or '按验收流程记录，用于确认设备内的个人数据已清除。'}",
                "情形九：因售后流程导致数据损坏。结论：按保修规则处理。",
                "情形十：退货前要退出账号吗。结论：需要，退出全部账号并恢复出厂设置。",
                "情形十一：云端空间不够怎么备份。结论：可先用本地电脑备份，再按需整理云端空间。",
                f"情形十二：换货的新机有迁移协助吗。结论：{n['migration_faq']}。",
                "情形十三：送修检测会清除数据吗。结论：检测过程可能恢复出厂设置，需提前备份。",
                "情形十四：备份完成后怎么核对。结论：核对联系人、照片、聊天记录与令牌类应用。",
            ),
        ),
        Section(
            "附录：数据备份深度问答",
            (
                "问题一：备份可以用厂商云空间吗？答复：可以，建议同时保留一份本地备份。",
                "问题二：备份失败怎么办？答复：可改用本地电脑备份，或联系售后协助确认备份状态。",
                "问题三：清除数据后还能找回吗？答复：恢复出厂设置后数据不可找回，需提前备份。",
                "问题四：数据备份有容量上限吗？答复：以云空间与本地存储容量为准。",
                "问题五：售后代为恢复出厂设置前会通知吗？答复：会按验收流程记录并执行。",
                "问题六：备份需要多长时间？答复：取决于数据量，建议在备份窗口内尽早完成。",
                "问题七：换货商品寄回前要解绑吗？答复：需要，解除设备绑定并退出全部账号。",
                "问题八：数据迁移可以远程协助吗？答复：以当前版本的迁移协助规则为准。",
                "问题九：清除报告的出具时机是什么？答复：在验收时按当前版本规则出具或记录。",
                "问题十：退货与送修的备份要求一样吗？答复：一样，都需备份并清除个人数据。",
                "问题十一：超过备份窗口还能补备份吗？答复：售后按流程推进，建议尽快联系售后确认。",
                f"问题十二：清除报告由谁出具？答复：{n['wipe_report'] or '按验收流程记录，当前版本未单独出具报告。'}",
                "问题十三：迁移协助额外收费吗？答复：以当前版本的迁移协助规则为准。",
                "问题十四：备份需要连网吗？答复：云端备份需要，本地备份不需要。",
                "问题十五：旧设备寄回前要解绑吗？答复：需要解除设备绑定并退出全部账号。",
                "问题十六：数据迁移要多久？答复：取决于数据量，建议在换货签收后尽快完成。",
                "问题十七：售后留痕包括哪些？答复：操作时间、操作事项与经办记录。",
                "问题十八：可以要求售后不接触数据吗？答复：可以，在寄回时备注并按最小必要原则处理。",
            ),
        ),
        Section(
            "附录：数据备份规则边界与例外",
            (
                "边界一：备份需在备份窗口内完成，超期未处理的按售后流程推进。",
                "边界二：恢复出厂设置后数据不可找回，需提前完成备份。",
                "边界三：寄回前需退出全部账号并解除设备绑定。",
                "边界四：检测过程可能恢复出厂设置，寄修前必须完成备份。",
                "边界五：售后按最小必要原则接触数据，全程留痕。",
                "边界六：清除报告按当前版本规则在验收时出具或记录。",
                "边界七：换货迁移协助范围以当前版本的迁移协助规则为准。",
                "边界八：外部存储可作为备份介质，建议同时保留两份。",
                "边界九：因售后流程导致数据损坏的，按保修规则处理。",
                "边界十：数据备份与清除规则以生效日期对应的版本为准。",
            ),
        ),
    )


# ============================================================ 数码商品退换货政策
def _digital_return_sections(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "生效与适用范围",
            (
                f"本政策适用于手机、平板、笔记本、耳机与智能穿戴等数码商品，自 {n['from_date']} 起生效。",
                "通用退货规则以《七天无理由退货政策（中国大陆）》为准，本政策仅补充数码品类的特殊约定。",
            ),
        ),
        Section(
            "七日无理由退货",
            (
                f"消费者自签收之日起七日内，可以在{n['activation_rule']}的前提下申请无理由退货。",
                n["activation_note"],
            ),
        ),
        Section(
            "激活判定",
            (
                "激活指首次开机联网、登录账号或完成系统绑定的行为。",
                "仅开机未联网、未登录账号的，视为未激活。",
            ),
        ),
        Section(
            "数据清除责任",
            (
                "退货或送修前，消费者需自行备份并清除设备内的个人数据。",
                f"因未清除数据导致的泄露，商城不承担责任；检测过程可能恢复出厂设置。{n['wipe_report']}",
            ),
        ),
        Section(
            "质量问题退换货",
            (
                "商品到货即损坏或七日内出现性能故障的，可申请退换货，运费由商城承担。",
                "质量问题需提供故障照片、视频或检测结论。",
            ),
        ),
        Section(
            "屏幕亮点标准",
            (
                "屏幕亮点数量在三个以内且分布在不同区域的，视为正常显示差异。",
                "亮点超过三个或集中在同一区域的，按显示质量问题处理。",
            ),
        ),
        Section(
            "配件与包装",
            (
                "退货需退回全部配件、数据线与原始包装，缺少配件按标价扣减。",
                "一次性封贴破损但商品未使用的，需经售后判定是否影响二次销售。",
            ),
        ),
        Section(
            "不予退换的情形",
            (
                n["not_returnable"],
                "错发、漏发或到货即损坏的不受上述限制。",
            ),
        ),
        Section(
            "退款时效",
            (
                "仓库验收通过后退款按原渠道退回，到账时间为一至七个工作日。",
                "分期订单退款优先冲抵未出账分期。",
            ),
        ),
        Section(
            "附录：数码退换常见问答",
            (
                "问题一：激活过的手机还能无理由退吗？答复：见激活与退货章节的当前规则。",
                "问题二：怎么判断是否已激活？答复：首次开机联网、登录账号或完成系统绑定即算激活。",
                "问题三：退货前要清除数据吗？答复：需要，需退出全部账号并恢复出厂设置。",
                "问题四：屏幕几个亮点算质量问题？答复：超过三个或集中在同一区域按显示质量问题处理。",
                "问题五：到货即损坏怎么退？答复：七日内可退换，运费由商城承担。",
                "问题六：退货要带哪些配件？答复：全部配件、数据线与原始包装。",
                "问题七：封贴破了能退吗？答复：需经售后判定是否影响二次销售。",
                "问题八：数码退款多久到账？答复：验收通过后一至七个工作日。",
                "问题九：分期买的数码怎么退？答复：优先冲抵未出账分期。",
                "问题十：忘记退出账号能退吗？答复：按当前激活规则处理，建议先退出全部账号。",
                "问题十一：耳机只开了机没联网算激活吗？答复：不算，仅开机未联网未登录视为未激活。",
                "问题十二：数据没清除泄露了怎么办？答复：商城不承担责任，请务必先备份并清除。",
                "问题十三：包装丢失能退吗？答复：原始包装缺失会影响二次销售判定。",
                "问题十四：性能故障怎么举证？答复：提供故障照片、视频或检测结论。",
                "问题十五：激活的平板有划痕能退吗？答复：外观问题按售后规则判定。",
                "问题十六：换货和退货哪个快？答复：同款有库存时换货优先，具体以售后审核为准。",
            ),
        ),
    ) + _digital_return_annex(n)


_DIGITAL_RETURN_OLD_N = dict[str, object](
    activation_rule="商品未激活、包装齐全",
    activation_note="商品一旦激活，即不支持无理由退货；已激活商品按保修与质量问题流程处理。",
    wipe_report="",
    not_returnable="已激活、已使用、超过七日窗口以及人为损坏的订单，不支持无理由退换。",
    from_date="2026 年 8 月 1 日",
)
_DIGITAL_RETURN_NEW_N = dict[str, object](
    activation_rule="系统功能完好、完成数据清除",
    activation_note="已激活但功能完好且已退出账号、清除数据的商品，仍适用七日无理由退货。",
    wipe_report="商城在验收时出具数据清除报告。",
    not_returnable="系统功能受损、已退出账号但数据未清除、超过七日窗口以及人为损坏的订单，不支持无理由退换。",
    from_date="2026 年 10 月 1 日",
)

DIGITAL_RETURN_OLD = _doc(
    "digital-return-policy",
    "数码商品退换货政策",
    doc_type="policy",
    version="2026.08.1",
    effective_from=_OLD_FROM,
    effective_to=_TO,
    knowledge_base=KB_CN,
    sections=_digital_return_sections(_DIGITAL_RETURN_OLD_N),
)

DIGITAL_RETURN_CURRENT = _doc(
    "digital-return-policy",
    "数码商品退换货政策",
    doc_type="policy",
    version="2026.10.1",
    effective_from=_NEW_FROM,
    knowledge_base=KB_CN,
    sections=_digital_return_sections(_DIGITAL_RETURN_NEW_N),
)


# ============================================================ 数码三包与保修条款
def _digital_warranty_sections(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "生效与适用范围",
            (
                f"本条款适用于数码类商品，自 {n['from_date']} 起生效。",
                "具体保修期以商品属性中的保修月数字段为准，不以聊天描述为准。",
            ),
        ),
        Section(
            "保修期限",
            (
                f"主机自签收之日起 {n['main_months']} 个月内保修，电池 {n['battery_months']} 个月，"
                f"屏幕 {n['screen_months']} 个月，随附配件 {n['accessory_months']} 个月。",
                "保修期自签收之日起计算，换货商品沿用原订单的保修截止日期。",
            ),
        ),
        Section(
            "保修范围",
            (
                "保修覆盖非人为因素导致的性能故障，包括无法开机、无法充电、触控失灵与异常断连。",
                "进液、跌落、私自拆机、非授权维修导致的损坏不在保修范围内。",
            ),
        ),
        Section(
            "电池专项",
            (
                f"电池在保修期内最大容量低于标称值百分之八十时，可申请{n['battery_action']}。",
                "电池循环损耗属于正常老化，不在保修范围内。",
            ),
        ),
        Section(
            "送修方式",
            (
                "支持寄修与指定服务点检测，寄修运费在保修范围内由商城承担。",
                "送修前需清除个人数据，检测过程可能恢复出厂设置。",
            ),
        ),
        Section(
            "保修凭证",
            (
                "保修以订单号或发票作为购买凭证，二者缺一不可时按订单支付记录判断。",
                "保修服务不随二手转让转移。",
            ),
        ),
        Section(
            "附录：数码保修常见问答",
            (
                f"问题一：数码主机保修多久？答复：{n['main_months']} 个月。",
                f"问题二：电池保修多久？答复：{n['battery_months']} 个月。",
                f"问题三：屏幕保修多久？答复：{n['screen_months']} 个月。",
                f"问题四：数据线等配件保修多久？答复：{n['accessory_months']} 个月。",
                f"问题五：电池健康低于多少能换？答复：低于标称值百分之八十可申请{n['battery_action']}。",
                "问题六：进液了还能保修吗？答复：进液不在保修范围内。",
                "问题七：私自拆机还能保修吗？答复：不在保修范围内。",
                "问题八：保修要什么凭证？答复：订单号或发票。",
                "问题九：二手数码能保修吗？答复：保修不随二手转让转移。",
                "问题十：寄修运费谁承担？答复：保修范围内由商城承担。",
                "问题十一：换货后保修怎么算？答复：沿用原订单的保修截止日期。",
                "问题十二：无法充电能保修吗？答复：非人为的性能故障在保修范围内。",
                "问题十三：屏幕坏点能保修吗？答复：按亮点标准判定，超标按显示质量问题处理。",
                "问题十四：保修检测要多久？答复：参照通用保修政策的检测周期。",
                "问题十五：配件丢了能单买保修吗？答复：配件丢失需重新购买。",
                "问题十六：蓝牙耳机断连能保修吗？答复：非人为的异常断连在保修范围内。",
            ),
        ),
    ) + _digital_warranty_annex(n)


_DIGITAL_WARRANTY_OLD_N = dict[str, object](
    main_months=12,
    battery_months=6,
    screen_months=6,
    accessory_months=3,
    battery_action="检测",
    detect_days="五至七个工作日",
    from_date="2026 年 8 月 1 日",
)
_DIGITAL_WARRANTY_NEW_N = dict[str, object](
    main_months=12,
    battery_months=12,
    screen_months=6,
    accessory_months=6,
    battery_action="检测更换",
    detect_days="三至五个工作日",
    from_date="2026 年 10 月 1 日",
)

DIGITAL_WARRANTY_OLD = _doc(
    "digital-warranty",
    "数码三包与保修条款",
    doc_type="warranty",
    version="2026.08.1",
    effective_from=_OLD_FROM,
    effective_to=_TO,
    knowledge_base=KB_CN,
    sections=_digital_warranty_sections(_DIGITAL_WARRANTY_OLD_N),
)

DIGITAL_WARRANTY_CURRENT = _doc(
    "digital-warranty",
    "数码三包与保修条款",
    doc_type="warranty",
    version="2026.10.1",
    effective_from=_NEW_FROM,
    knowledge_base=KB_CN,
    sections=_digital_warranty_sections(_DIGITAL_WARRANTY_NEW_N),
)


# ============================================================ 数码发票与价保规则
def _digital_invoice_price_sections(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "适用范围",
            (
                f"本规则适用于数码类商品的发票开具与价格保护申请，自 {n['from_date']} 起生效。",
                "通用开票规则以《发票开具与补开规则》为准。",
            ),
        ),
        Section(
            f"{n['pp_days']}日价保",
            (
                f"数码类商品自订单支付成功之日起 {n['pp_days']} 日内降价的，可申请价格保护。",
                "价保比价以同款同配置的页面标价为准。",
            ),
        ),
        Section(
            "价保条件",
            (
                "申请价保的订单不得已退货或已取消，且需为同款同配置同颜色。",
                "使用优惠券、限时秒杀产生的价差不在价保范围内。",
            ),
        ),
        Section(
            "补开发票",
            (
                f"数码类订单完成后 {n['invoice_days']} 日内可申请补开发票，超期需人工评估。",
                "已激活商品的发票信息以订单支付记录为准。",
            ),
        ),
        Section(
            "价保方式",
            (
                f"价保差额以{n['pp_refund']}方式返还，优惠券有效期为三十天。",
                "同一订单同一商品仅补偿一次。",
            ),
        ),
        Section(
            "附录：数码价保常见问答",
            (
                f"问题一：数码价保多久？答复：{n['pp_days']} 日。",
                f"问题二：价保差额怎么返？答复：以{n['pp_refund']}方式返还。",
                f"问题三：数码订单多久能补开发票？答复：完成后 {n['invoice_days']} 日内。",
                "问题四：价保要同配置吗？答复：需要同款同配置同颜色。",
                "问题五：秒杀价能价保吗？答复：不在价保范围内。",
                "问题六：价保能补几次？答复：次数不限，同一商品仅补偿一次。",
                "问题七：激活后还能补开发票吗？答复：可以，以订单支付记录为准。",
                "问题八：优惠券能用于价保比价吗？答复：券造成的价差不在价保范围内。",
                "问题九：价保补偿的券有效期多久？答复：三十天。",
                "问题十：退货后价保怎么办？答复：补偿与实际退款分别计算。",
                "问题十一：数码价保含运费吗？答复：比价不含运费与增值服务。",
                "问题十二：补开票要什么材料？答复：订单号与开票信息。",
            ),
        ),
    ) + _digital_invoice_annex(n)


_DIGITAL_INVOICE_OLD_N = dict[str, object](
    pp_days=3,
    invoice_days=45,
    pp_refund="优惠券",
    from_date="2026 年 8 月 1 日",
)
_DIGITAL_INVOICE_NEW_N = dict[str, object](
    pp_days=7,
    invoice_days=90,
    pp_refund="优惠券或原路退款",
    from_date="2026 年 10 月 1 日",
)

DIGITAL_INVOICE_PRICE_OLD = _doc(
    "digital-invoice-price",
    "数码发票与价保规则",
    doc_type="invoice",
    version="2026.08.1",
    effective_from=_OLD_FROM,
    effective_to=_TO,
    knowledge_base=KB_CN,
    sections=_digital_invoice_price_sections(_DIGITAL_INVOICE_OLD_N),
)

DIGITAL_INVOICE_PRICE_CURRENT = _doc(
    "digital-invoice-price",
    "数码发票与价保规则",
    doc_type="invoice",
    version="2026.10.1",
    effective_from=_NEW_FROM,
    knowledge_base=KB_CN,
    sections=_digital_invoice_price_sections(_DIGITAL_INVOICE_NEW_N),
)


# ============================================================ 数码数据备份与迁移指引
def _digital_backup_sections(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "适用范围",
            (
                f"本指引说明数码商品在退货、换货与送修前的数据备份要求，自 {n['from_date']} 起生效。",
                "指引不替代设备系统的备份功能说明。",
            ),
        ),
        Section(
            "备份窗口",
            (
                f"送修申请提交后，消费者有 {n['backup_days']} 时间完成数据备份与清除。",
                "超过备份窗口未处理的，售后按流程推进检测，数据丢失风险由消费者承担。",
            ),
        ),
        Section(
            "备份方式",
            (
                "可使用设备厂商云空间、本地电脑备份或外部存储完成备份。",
                "备份完成后建议核对联系人、照片、聊天记录与令牌类应用。",
            ),
        ),
        Section(
            "清除要求",
            (
                "寄回前需退出全部账号、解除设备绑定并恢复出厂设置。",
                f"未清除数据的设备，售后在检测前代为恢复出厂设置。{n['wipe_report']}",
            ),
        ),
        Section(
            "换机迁移",
            (
                "换货商品签收后，消费者可自行完成数据迁移。",
                n["migration_help"],
            ),
        ),
        Section(
            "数据安全",
            (
                "售后接触设备的人员按最小必要原则操作，全程留痕。",
                "因售后流程导致的数据损坏，按保修规则处理。",
            ),
        ),
        Section(
            "附录：数据备份常见问答",
            (
                f"问题一：送修前多久内要完成备份？答复：{n['backup_days']}。",
                f"问题二：换货后有迁移协助吗？答复：{n['migration_faq']}",
                "问题三：怎么备份最稳妥？答复：云空间加本地备份各一份，并核对令牌类应用。",
                "问题四：没清除数据会怎样？答复：售后在检测前会代为恢复出厂设置。",
                "问题五：数据损坏能赔吗？答复：因售后流程导致的按保修规则处理。",
                "问题六：哪些数据容易漏？答复：聊天记录、照片与令牌类应用。",
                "问题七：外部存储可以作为备份吗？答复：可以，建议备份两份。",
                "问题八：换货的新机怎么迁数据？答复：消费者可自行迁移，也可申请协助。",
                "问题九：售后会看我的数据吗？答复：按最小必要原则操作并全程留痕。",
                "问题十：退货前要退出账号吗？答复：需要，退出全部账号并恢复出厂设置。",
                "问题十一：备份窗口过了怎么办？答复：售后按流程推进，数据风险自担。",
                "问题十二：清除报告有什么用？答复：用于确认设备内的个人数据已清除。",
            ),
        ),
    ) + _digital_backup_annex(n)


_DIGITAL_BACKUP_OLD_N = dict[str, object](
    backup_days="五日",
    wipe_report="",
    migration_help="商城不提供云端迁移协助服务。",
    migration_faq="暂不提供云端迁移协助",
    from_date="2026 年 8 月 1 日",
)
_DIGITAL_BACKUP_NEW_N = dict[str, object](
    backup_days="七日",
    wipe_report="商城在验收时出具数据清除报告。",
    migration_help="每笔订单首次换货可申请一次免费的云端迁移协助，由售后远程指导。",
    migration_faq="每笔订单首次换货可申请一次免费的云端迁移协助",
    from_date="2026 年 10 月 1 日",
)

DIGITAL_DATA_BACKUP_OLD = _doc(
    "digital-data-backup",
    "数码数据备份与迁移指引",
    doc_type="policy",
    version="2026.08.1",
    effective_from=_OLD_FROM,
    effective_to=_TO,
    knowledge_base=KB_CN,
    sections=_digital_backup_sections(_DIGITAL_BACKUP_OLD_N),
)

DIGITAL_DATA_BACKUP_CURRENT = _doc(
    "digital-data-backup",
    "数码数据备份与迁移指引",
    doc_type="policy",
    version="2026.10.1",
    effective_from=_NEW_FROM,
    knowledge_base=KB_CN,
    sections=_digital_backup_sections(_DIGITAL_BACKUP_NEW_N),
)

# ============================================================ 历史版本（2024 / 2025）
# A full four-step version chain per document so "the same question, a
# different answer" is testable at four dates. Adjacent versions always differ
# on at least one number.
_DIGITAL_RETURN_2024_N = dict[str, object](
    activation_rule="商品未激活、包装齐全",
    activation_note="商品一旦激活，即不支持无理由退货；已激活商品按保修与质量问题流程处理。",
    wipe_report="",
    not_returnable="已激活、已使用、超过七日窗口以及人为损坏的订单，不支持无理由退换。",
    from_date="2024 年 3 月 1 日",
)
_DIGITAL_RETURN_2025_N = dict[str, object](
    activation_rule="系统功能完好、完成数据清除",
    activation_note="已激活但功能完好且已退出账号、清除数据的商品，仍适用七日无理由退货。",
    wipe_report="",
    not_returnable="系统功能受损、数据未清除、超过七日窗口以及人为损坏的订单，不支持无理由退换。",
    from_date="2025 年 3 月 1 日",
)

DIGITAL_RETURN_2024 = _doc(
    "digital-return-policy",
    "数码商品退换货政策",
    doc_type="policy",
    version="2024.1",
    effective_from="2024-03-01T00:00:00Z",
    effective_to="2025-03-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_digital_return_sections(_DIGITAL_RETURN_2024_N),
)
DIGITAL_RETURN_2025 = _doc(
    "digital-return-policy",
    "数码商品退换货政策",
    doc_type="policy",
    version="2025.1",
    effective_from="2025-03-01T00:00:00Z",
    effective_to="2026-08-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_digital_return_sections(_DIGITAL_RETURN_2025_N),
)

_DIGITAL_WARRANTY_2024_N = dict[str, object](
    main_months=12,
    battery_months=6,
    screen_months=3,
    accessory_months=3,
    battery_action="检测",
    detect_days="十至十五个工作日",
    from_date="2024 年 3 月 1 日",
)
_DIGITAL_WARRANTY_2025_N = dict[str, object](
    main_months=12,
    battery_months=6,
    screen_months=6,
    accessory_months=3,
    battery_action="检测",
    detect_days="七至十个工作日",
    from_date="2025 年 3 月 1 日",
)
DIGITAL_WARRANTY_2024 = _doc(
    "digital-warranty",
    "数码三包与保修条款",
    doc_type="warranty",
    version="2024.1",
    effective_from="2024-03-01T00:00:00Z",
    effective_to="2025-03-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_digital_warranty_sections(_DIGITAL_WARRANTY_2024_N),
)
DIGITAL_WARRANTY_2025 = _doc(
    "digital-warranty",
    "数码三包与保修条款",
    doc_type="warranty",
    version="2025.1",
    effective_from="2025-03-01T00:00:00Z",
    effective_to="2026-08-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_digital_warranty_sections(_DIGITAL_WARRANTY_2025_N),
)

_DIGITAL_INVOICE_2024_N = dict[str, object](
    pp_days=3,
    invoice_days=30,
    pp_refund="优惠券",
    from_date="2024 年 3 月 1 日",
)
_DIGITAL_INVOICE_2025_N = dict[str, object](
    pp_days=3,
    invoice_days=60,
    pp_refund="优惠券",
    from_date="2025 年 3 月 1 日",
)
DIGITAL_INVOICE_PRICE_2024 = _doc(
    "digital-invoice-price",
    "数码发票与价保规则",
    doc_type="invoice",
    version="2024.1",
    effective_from="2024-03-01T00:00:00Z",
    effective_to="2025-03-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_digital_invoice_price_sections(_DIGITAL_INVOICE_2024_N),
)
DIGITAL_INVOICE_PRICE_2025 = _doc(
    "digital-invoice-price",
    "数码发票与价保规则",
    doc_type="invoice",
    version="2025.1",
    effective_from="2025-03-01T00:00:00Z",
    effective_to="2026-08-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_digital_invoice_price_sections(_DIGITAL_INVOICE_2025_N),
)

_DIGITAL_BACKUP_2024_N = dict[str, object](
    backup_days="一日",
    wipe_report="",
    migration_help="商城不提供数据迁移协助。",
    migration_faq="暂不提供数据迁移协助",
    from_date="2024 年 3 月 1 日",
)
_DIGITAL_BACKUP_2025_N = dict[str, object](
    backup_days="三日",
    wipe_report="",
    migration_help="商城不提供云端迁移协助服务。",
    migration_faq="暂不提供云端迁移协助",
    from_date="2025 年 3 月 1 日",
)
DIGITAL_DATA_BACKUP_2024 = _doc(
    "digital-data-backup",
    "数码数据备份与迁移指引",
    doc_type="policy",
    version="2024.1",
    effective_from="2024-03-01T00:00:00Z",
    effective_to="2025-03-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_digital_backup_sections(_DIGITAL_BACKUP_2024_N),
)
DIGITAL_DATA_BACKUP_2025 = _doc(
    "digital-data-backup",
    "数码数据备份与迁移指引",
    doc_type="policy",
    version="2025.1",
    effective_from="2025-03-01T00:00:00Z",
    effective_to="2026-08-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_digital_backup_sections(_DIGITAL_BACKUP_2025_N),
)

DIGITAL_DOCS: tuple[PolicyDoc, ...] = (
    DIGITAL_RETURN_2024,
    DIGITAL_RETURN_2025,
    DIGITAL_RETURN_OLD,
    DIGITAL_RETURN_CURRENT,
    DIGITAL_WARRANTY_2024,
    DIGITAL_WARRANTY_2025,
    DIGITAL_WARRANTY_OLD,
    DIGITAL_WARRANTY_CURRENT,
    DIGITAL_INVOICE_PRICE_2024,
    DIGITAL_INVOICE_PRICE_2025,
    DIGITAL_INVOICE_PRICE_OLD,
    DIGITAL_INVOICE_PRICE_CURRENT,
    DIGITAL_DATA_BACKUP_2024,
    DIGITAL_DATA_BACKUP_2025,
    DIGITAL_DATA_BACKUP_OLD,
    DIGITAL_DATA_BACKUP_CURRENT,
)
