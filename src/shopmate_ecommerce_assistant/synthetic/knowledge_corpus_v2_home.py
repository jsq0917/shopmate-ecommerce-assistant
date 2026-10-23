"""Stage-17 corpus expansion — home & furniture (家居) category documents.

Four synthetic policy documents, authored once as parameterised builders and
instantiated twice: a superseded version and a current version that differ on
the numbers retrieval must respect (return window 7 vs 15 days, free first
pickup, structure warranty 12 vs 24 months, price-protection 3 vs 7 days,
delivery booking lead time 3 vs 2 days).

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
def _furniture_return_annex(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "附录：大家具退换情形速查",
            (
                f"情形一：床架签收第五日申请无理由退货。结论：未安装、未使用且包装齐全，在 {n['window']} 日窗口内可退。",
                "情形二：沙发已上门安装，使用一周后想退。结论：安装后影响二次销售，不支持无理由退货。",
                f"情形三：餐桌到货即桌腿开裂。结论：属于质量问题，{n['quality_window']} 日内可退换，往返运费由商城承担。",
                f"情形四：退货时承运商上门取件收费吗。结论：{n['pickup_fee']}。",
                "情形五：岩板台面纹理与页面不一致。结论：天然纹理差异不算质量问题，明显色差需同光源对比照片。",
                "情形六：床垫塌陷能退吗。结论：属于质量问题，在退换窗口内按检测结论处理。",
                f"情形七：大家具退款多久到账。结论：验收通过后 {n['refund_days']}。",
                "情形八：退货时安装说明书丢失。结论：配件缺失按标价扣减，建议随货备齐。",
                "情形九：安装服务完成后安装费能退吗。结论：安装完成后安装费用不予退还。",
                "情形十：预售大家具的窗口从哪天算。结论：自实际签收之日起计算。",
                "情形十一：书柜层板变形能换吗。结论：结构件问题在退换或保修窗口内可申请处理。",
                "情形十二：错发的家居商品。结论：不受安装与窗口限制，按错发规则处理。",
                "情形十三：部分部件损坏能只换部件吗。结论：需整单退换，不支持部件拆分。",
                "情形十四：颜色和页面差很多。结论：提供同光源对比照片，由售后判定。",
                "情形十五：无电梯楼层取件另收费吗。结论：搬运与取件费用以承运商报价为准。",
                "情形十六：超过退换窗口的损坏还能处理吗。结论：可按保修政策处理，需检测结论。",
            ),
        ),
        Section(
            "附录：大家具退换深度问答",
            (
                "问题一：退货申请提交后多久审核？答复：一个工作日内给出审核结论。",
                "问题二：无理由退货和质量问题退货能互相改吗？答复：审核通过前可联系售后变更。",
                "问题三：大家具退货的物流单号填错怎么办？答复：在售后入口更新物流信息，超时未更新申请可能关闭。",
                "问题四：取件时家里有人必须到场吗？答复：需要成年人在场确认商品状态。",
                "问题五：退货包裹内放纸条注明订单号可以吗？答复：可以，建议同时在订单页提交物流信息。",
                "问题六：退款金额和实付不一致怎么查？答复：退款明细列示取件费与配件扣减项。",
                "问题七：大家具可以寄到付吗？答复：不支持，需按售后提供的地址寄回并保留单号。",
                "问题八：安装后发现商品与页面色差明显怎么办？答复：提供同光源对比照片申请复核。",
                "问题九：床架螺丝孔位对不上算谁的责任？答复：属于配件或结构问题，在退换窗口内可按质量问题处理。",
                "问题十：退货后赠品要退吗？答复：需要，赠品缺失按标价扣减。",
                "问题十一：部分部件生锈能整单退吗？答复：五金件锈蚀不在保修范围，退换按窗口与商品状态判定。",
                "问题十二：无理由退货的床垫需要原包装吗？答复：需要，包装缺失会影响二次销售判定。",
                "问题十三：两个订单的大家具能一起取件吗？答复：需分别提交申请，取件按订单计费。",
                "问题十四：取件后商品在运输中损坏怎么办？答复：保留包装与照片，由售后与承运商核查。",
                "问题十五：超过取件预约时间没来怎么办？答复：联系售后重新预约，长时间未取件的申请可能关闭。",
                "问题十六：退款是原路返回吗？答复：按原支付渠道退回。",
                "问题十七：退货运费险能保大家具吗？答复：大件取件费用按本政策执行，不在运费险范围。",
                "问题十八：定制定尺寸的餐桌能退吗？答复：定制品不适用无理由退换。",
                "问题十九：发票需要随货寄回吗？答复：电子发票无需退回，纸质发票按售后指引处理。",
                "问题二十：复核结论多久出？答复：复核由售后人工完成，以工单记录为准。",
            ),
        ),
        Section(
            "附录：退换规则边界与例外",
            (
                "边界一：退换窗口的起算日以物流签收记录为准。",
                "边界二：已安装或已使用的大家具不适用无理由退换。",
                "边界三：质量问题退换不受安装状态限制。",
                "边界四：取件按订单分别预约，费用按订单计收。",
                "边界五：复核期间不重复发起退款。",
                "边界六：预售大家具的窗口自实际签收之日起算。",
                "边界七：配件缺失按标价从退款中扣减。",
                "边界八：大家具退换需整单处理，不支持部件拆分。",
                "边界九：色差与材质差异的判定以当前版本规则为准。",
                "边界十：退换规则以生效日期对应的版本为准。",
            ),
        ),
    )


def _furniture_warranty_annex(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "附录：家居保修情形速查",
            (
                f"情形一：沙发框架使用第十三个月开裂。结论：结构件保修 {n['structure_months']} 个月，期内可申请。",
                f"情形二：抽屉滑轨使用第七个月失效。结论：五金件保修 {n['hardware_months']} 个月，期内可保修。",
                f"情形三：床垫使用第十四个月弹簧塌陷。结论：床垫 {n['mattress_months']} 个月内可申请检测。",
                f"情形四：保修检测要等多久。结论：{n['detect_days']}。",
                "情形五：实木桌面长期日晒后开裂。结论：保养不当导致的损坏不在保修范围内。",
                "情形六：柜门铰链锈蚀。结论：潮湿环境导致的锈蚀不在保修范围内。",
                "情形七：餐桌腿被重物压弯。结论：超负荷使用导致的人为损坏不在保修范围内。",
                "情形八：搬家后还能保修吗。结论：可以，保修不因搬迁失效。",
                "情形九：更换的部件保修多久。结论：沿用原订单的保修截止日期。",
                "情形十：软包污损能保修吗。结论：污损不属于保修范围。",
                "情形十一：保修期内会上门检测吗。结论：由售后确认是否需要上门检测。",
                "情形十二：餐桌腿松了能修吗。结论：结构件保修期内可申请。",
                "情形十三：柜门关不上能保修吗。结论：五金件问题在保修期内可申请。",
                "情形十四：床垫被烫出洞能保修吗。结论：烧伤不在保修范围内。",
                "情形十五：实木家具怎么保养。结论：避免日晒与潮湿，每半年紧固连接件。",
                "情形十六：软体家具怎么保养。结论：定期翻转使用，避免局部长期受压。",
            ),
        ),
        Section(
            "附录：家居保修深度问答",
            (
                "问题一：保修申请提交后多久受理？答复：一个工作日内给出受理结论。",
                "问题二：保修期内可以付费加速处理吗？答复：可以，维修前会给出报价。",
                "问题三：保修期间商品寄回的运费谁出？答复：保修范围内的寄修运费由商城承担。",
                "问题四：实木家具出现裂纹怎么判断是质量问题？答复：由售后依照片与检测结论判定，超负荷与保养不当不在范围。",
                "问题五：床垫污损和塌陷能分别处理吗？答复：污损不在保修范围，塌陷按床垫专项检测。",
                "问题六：五金件锈蚀能自费更换吗？答复：可以，按付费维修处理并给出报价。",
                "问题七：保修换新和维修怎么选？答复：同款有配件时优先维修，无法维修时可申请换新。",
                "问题八：保修期内商品可以转让吗？答复：保修服务不随二手转让转移。",
                "问题九：多次故障能反复保修吗？答复：同一故障修复后不重复保修，新故障可再次申请。",
                "问题十：上门检测需要准备什么？答复：订单号、损坏照片与可用的上门时间。",
                "问题十一：检测结论有异议怎么办？答复：可申请复核，复核结论以工单记录为准。",
                "问题十二：结构件保修期和五金件不同怎么办？答复：按各自保修期分别判定。",
                "问题十三：床垫的检测结论多久出？答复：按当前版本的检测周期执行。",
                "问题十四：保修更换的部件运输损坏谁负责？答复：由商城承担返修运输风险。",
                "问题十五：商品在保修期内停产了怎么办？答复：以功能等效的配件或方案替代。",
                "问题十六：保修需要寄回原包装吗？答复：不需要，但需做好运输防护。",
                "问题十七：保修期会因为维修而延长吗？答复：不会，保修不延长原保修期。",
                "问题十八：非保修范围的损坏维修后保修多久？答复：按维修报价单约定执行。",
            ),
        ),
        Section(
            "附录：保修规则边界与例外",
            (
                "边界一：保修期以物流签收记录起算。",
                "边界二：更换部件沿用原订单的保修截止日期。",
                "边界三：保养要求以本条款为准，聊天描述不构成承诺。",
                "边界四：结构件与五金件按各自保修期分别判定。",
                "边界五：床垫专项检测按检测结论处理。",
                "边界六：同一故障修复后不重复保修。",
                "边界七：超出保修期的损坏按付费维修处理。",
                "边界八：保修不因消费者搬迁而失效。",
                "边界九：检测周期以当前生效版本为准。",
                "边界十：保修条款以生效日期对应的版本为准。",
            ),
        ),
    )


def _furniture_invoice_annex(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "附录：家居价保情形速查",
            (
                f"情形一：床架支付后第五日同款降价。结论：在 {n['pp_days']} 日价保期内可申请。",
                f"情形二：价保差额怎么返。结论：以{n['pp_refund']}方式返还，优惠券有效期三十天。",
                f"情形三：家居订单完成第六十天想补开发票。结论：{n['invoice_days']} 日内可补开，超期人工评估。",
                "情形四：安装费能开在发票里吗。结论：包含在实付金额内，按商品明细合并开具。",
                "情形五：单独买的安装服务怎么开票。结论：按服务项目开具。",
                "情形六：价保需要同规格吗。结论：需要同款同规格同颜色。",
                "情形七：大家具降价能价保吗。结论：在价保期内同款同规格降价可申请。",
                "情形八：价保能补几次。结论：次数不限，同一商品仅补偿一次。",
                "情形九：退货后价保补偿怎么办。结论：补偿与实际退款分别计算。",
                "情形十：跨月订单能补票吗。结论：在补开期限内可申请，超期人工评估。",
                "情形十一：运费计入发票金额吗。结论：自营运费包含在实付金额内。",
                "情形十二：电子发票多久开出。结论：参照通用开票规则的时效。",
                "情形十三：使用优惠券的价差能价保吗。结论：不在价保范围内。",
                "情形十四：秒杀价能价保吗。结论：限时秒杀产生的价差不在价保范围内。",
            ),
        ),
        Section(
            "附录：家居价保深度问答",
            (
                "问题一：价保申请提交后多久出结论？答复：系统自动比价后在一个工作日内给出结论。",
                "问题二：价保补偿可以提现吗？答复：按当前版本的返还方式执行，优惠券形式不可提现。",
                "问题三：多件商品能合并价保吗？答复：按订单内商品分别比价，分别补偿。",
                "问题四：价保比价要同店铺吗？答复：需同一店铺同一商品同一规格。",
                "问题五：部分退款后还能价保吗？答复：订单未取消且在价保期内可申请。",
                "问题六：价保失败能申诉吗？答复：可提交页面截图申请复核。",
                "问题七：补开发票要什么材料？答复：订单号与开票信息。",
                "问题八：专用发票能补开吗？答复：可申请，需提交企业资质并经审核。",
                "问题九：跨年度发票红冲怎么处理？答复：由财务在申报期内按税务要求处理。",
                "问题十：价保和退换货能同时进行吗？答复：可以，分别计算。",
                "问题十一：安装费的发票能单独开吗？答复：按服务项目开具。",
                "问题十二：红冲后重开的发票金额怎么算？答复：按实际支付金额重新开具。",
                "问题十三：价保补偿的优惠券能叠加使用吗？答复：按优惠券使用规则执行。",
                "问题十四：订单取消后已开票怎么办？答复：需先红冲原发票，再按实际金额处理。",
                "问题十五：补开票的抬头可以改吗？答复：开票当月可申请换开，跨月需先红冲再重开。",
                "问题十六：电子发票的法律效力？答复：与纸质普通发票具有同等效力。",
                "问题十七：价保申请能撤销吗？答复：结论出具前可撤销，重新提交需在价保期内。",
                "问题十八：搬运费计入发票金额吗？答复：按实付金额合并开具，明细单独列示。",
            ),
        ),
        Section(
            "附录：价保规则边界与例外",
            (
                "边界一：价保比价以页面标价为准，不含搬运费与增值服务。",
                "边界二：价保期限自订单支付成功之日起算。",
                "边界三：价保补偿与实际退款分别计算。",
                "边界四：配送与安装费按商品明细合并开具。",
                "边界五：发票红冲需先于重开办理。",
                "边界六：补开期限以当前生效版本为准。",
                "边界七：优惠券与秒杀价差不适用价保。",
                "边界八：价保比价需同店铺同款同规格。",
                "边界九：单独购买的安装服务按服务项目开票。",
                "边界十：价保规则以生效日期对应的版本为准。",
            ),
        ),
    )


def _furniture_delivery_annex(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "附录：送装情形速查",
            (
                f"情形一：预约后多久上门送货。结论：{n['lead_days']}。",
                f"情形二：送货晚了有补偿吗。结论：{n['compensation_faq']}。",
                "情形三：安装费怎么收。结论：按件计收，结算页展示。",
                "情形四：搬运费怎么算。结论：无电梯楼层按楼层收取。",
                f"情形五：装好后螺丝松了怎么办。结论：{n['retighten_days']}内可免费复紧一次。",
                "情形六：可以自己约时间吗。结论：可在订单备注期望时段，以预约电话确认为准。",
                "情形七：外包装破损怎么办。结论：当场拍照并拒收。",
                "情形八：签收单有什么用。结论：作为安装服务完成的凭证。",
                "情形九：入户摆放另外收费吗。结论：搬运范围仅限入户，不含摆放与组装。",
                "情形十：安装包含哪些项目。结论：以商品说明书列明的项目为准。",
                "情形十一：送装可以分开预约吗。结论：需在送货时一并预约安装。",
                "情形十二：安装费开票吗。结论：包含在实付金额内合并开具。",
                "情形十三：改约上门时间收费吗。结论：以承运商报价为准，改约需提前一个工作日。",
                "情形十四：安装后多久内可以申请复紧。结论：按当前版本的复紧期限执行。",
            ),
        ),
        Section(
            "附录：送装深度问答",
            (
                "问题一：改约上门时间收费吗？答复：以承运商报价为准，改约需提前一个工作日。",
                "问题二：复紧申请要付费吗？答复：复紧期限内免费一次。",
                "问题三：安装完成后可以当场验收吗？答复：可以，安装完成后签收单作为凭证。",
                "问题四：无电梯楼层搬楼怎么收费？答复：按楼层收取，标准以承运商报价为准。",
                "问题五：可以指定送货时段吗？答复：可备注期望时段，以预约电话确认为准。",
                "问题六：送装订单能部分拒收吗？答复：需当面验收整单，部分拒收按错发规则处理。",
                "问题七：安装人员上门需要做什么准备？答复：清理通行路径并确认水电位置。",
                "问题八：安装完成后发现商品损坏怎么办？答复：当场拍照并联系售后，按质量问题处理。",
                "问题九：送货时间可以改到晚上吗？答复：以承运商预约时段为准。",
                "问题十：安装服务能单独购买吗？答复：可以，按服务项目计费。",
                "问题十一：大家具能送到楼下自提吗？答复：搬运范围仅限入户，不含摆放与组装。",
                "问题十二：预约电话漏接怎么办？答复：承运商会再次联系，也可在订单页更新联系方式。",
                "问题十三：安装后的包装物要保留吗？答复：建议保留至复紧期限结束。",
                "问题十四：超时未上门的补偿怎么发放？答复：以当前版本的补偿规则为准。",
                "问题十五：送装可以拆成两次服务吗？答复：需在送货时一并预约安装。",
                "问题十六：安装费能退吗？答复：安装完成后不予退还。",
                "问题十七：搬运途中商品损坏谁负责？答复：由商城与承运商核查后按责任处理。",
                "问题十八：复紧申请需要什么材料？答复：订单号与安装完成凭证。",
            ),
        ),
        Section(
            "附录：送装规则边界与例外",
            (
                "边界一：上门时间以预约电话确认为准，备注时段仅供参考。",
                "边界二：安装需在送货时一并预约。",
                "边界三：搬运范围仅限入户，不含摆放与组装。",
                "边界四：安装完成后安装费用不予退还。",
                "边界五：复紧期限内免费一次，超期按售后规则处理。",
                "边界六：外包装破损应当场拍照并拒收。",
                "边界七：签收单作为安装服务完成的凭证。",
                "边界八：无电梯楼层搬运费以承运商报价为准。",
                "边界九：超时补偿以当前生效版本为准。",
                "边界十：送装规则以生效日期对应的版本为准。",
            ),
        ),
    )


# ============================================================ 大件家居退换货政策
def _furniture_return_sections(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "生效与适用范围",
            (
                f"本政策适用于床架、床垫、沙发、餐桌椅、书柜等大件家居商品，自 {n['from_date']} 起生效。",
                "小件家居百货适用通用退货政策，本政策仅约束大件品类。",
            ),
        ),
        Section(
            f"{n['window']}日无理由退货",
            (
                f"消费者自签收之日起 {n['window']} 日内，可以在商品未安装、未使用、包装齐全的前提下申请无理由退货。",
                "已上门安装或已使用的大家具，因影响二次销售不支持无理由退货。",
            ),
        ),
        Section(
            "质量问题退换货",
            (
                f"商品到货即损坏、结构失稳或部件缺失的，自签收之日起 {n['quality_window']} 日内可申请退换货。",
                "质量问题退换货的往返运费由商城承担。",
            ),
        ),
        Section(
            "上门取件",
            (
                f"大件退货由上门的承运商取件，{n['pickup_fee']}。",
                "取件前需保持商品可移动状态，消费者需自行拆除已安装的简易部件。",
            ),
        ),
        Section(
            "色差与材质差异",
            (
                "实木与岩板材质的天然纹理、色泽存在合理差异，不属于质量问题。",
                f"与页面展示相比明显色差需提供同光源对比照片；{n['color_rule']}",
            ),
        ),
        Section(
            "配件与赠品",
            (
                "退货时需退回全部配件、五金件、安装说明书与赠品，缺少配件按标价扣减。",
                "安装服务一旦完成，安装费用不予退还。",
            ),
        ),
        Section(
            "不予退换的情形",
            (
                "已安装、已使用、人为损坏以及超过退换窗口的订单，不支持无理由退换。",
                "错发、漏发或到货即损坏的不受上述限制。",
            ),
        ),
        Section(
            "退款时效",
            (
                f"仓库验收通过后退款按原渠道退回，大件退款到账时间为 {n['refund_days']}。",
                "取件服务费与配件扣减在退款明细中单独列示。",
            ),
        ),
        Section(
            "附录：大家具退换常见问答",
            (
                f"问题一：大家具无理由退货窗口是多久？答复：{n['window']} 日。",
                f"问题二：上门取件收费吗？答复：{n['pickup_faq']}",
                "问题三：已安装的沙发能退吗？答复：不能，安装后影响二次销售。",
                f"问题四：到货损坏的退换窗口呢？答复：{n['quality_window']} 日内。",
                f"问题五：大家具退款多久到账？答复：{n['refund_days']}。",
                "问题六：岩板纹理和页面不一样算质量问题吗？答复：天然纹理差异不算，明显色差可判定。",
                "问题七：退货要保留哪些东西？答复：全部配件、五金件、说明书与赠品。",
                "问题八：安装费能退吗？答复：安装完成后安装费用不予退还。",
                "问题九：床垫塌陷能换吗？答复：属于质量问题，在退换窗口内可处理。",
                "问题十：缺少配件怎么扣款？答复：按配件标价从退款中扣减。",
                "问题十一：可以只退一件大家具的部分部件吗？答复：需整单退换，不支持部件拆分。",
                "问题十二：取件前要做什么准备？答复：商品保持可移动状态，自行拆除简易安装部件。",
                "问题十三：预售大家具的窗口从哪天算？答复：自实际签收之日起计算。",
                "问题十四：质量问题退货运费谁承担？答复：往返运费由商城承担。",
                "问题十五：超过窗口的损坏还能处理吗？答复：可按保修政策处理，需检测结论。",
                "问题十六：颜色和页面差很多怎么办？答复：提供同光源对比照片，由售后判定。",
            ),
        ),
    ) + _furniture_return_annex(n)


_FURNITURE_RETURN_OLD_N = dict[str, object](
    window=7,
    quality_window=15,
    pickup_fee="每次取件收取 50 元服务费，费用从退款金额中扣除",
    pickup_faq="每次收取 50 元，从退款中扣除",
    color_rule="主张明显色差需提供同光源对比照片，由售后判定。",
    refund_days="三至十个工作日",
    from_date="2026 年 8 月 1 日",
)
_FURNITURE_RETURN_NEW_N = dict[str, object](
    window=15,
    quality_window=30,
    pickup_fee="每笔订单首次取件免收服务费，再次取件收取 50 元",
    pickup_faq="每笔订单首次免收，再次收取 50 元",
    color_rule="色差超出行业公差（色差 ΔE 大于 3.0）时视为质量问题。",
    refund_days="一至七个工作日",
    from_date="2026 年 10 月 1 日",
)

FURNITURE_RETURN_OLD = _doc(
    "furniture-return-policy",
    "大件家居退换货政策",
    doc_type="policy",
    version="2026.08.1",
    effective_from=_OLD_FROM,
    effective_to=_TO,
    knowledge_base=KB_CN,
    sections=_furniture_return_sections(_FURNITURE_RETURN_OLD_N),
)

FURNITURE_RETURN_CURRENT = _doc(
    "furniture-return-policy",
    "大件家居退换货政策",
    doc_type="policy",
    version="2026.10.1",
    effective_from=_NEW_FROM,
    knowledge_base=KB_CN,
    sections=_furniture_return_sections(_FURNITURE_RETURN_NEW_N),
)


# ============================================================ 家居结构保修与保养要求
def _furniture_warranty_sections(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "生效与适用范围",
            (
                f"本条款适用于大件家居商品，自 {n['from_date']} 起生效。",
                "保修范围以本条款为准，聊天中的描述不构成保修承诺。",
            ),
        ),
        Section(
            "结构件保修",
            (
                f"床架、沙发框架、桌腿与柜体骨架等结构件自签收之日起 {n['structure_months']} 个月内出现开裂、松脱的，可申请保修。",
                "结构件因超负荷使用、不当搬运导致的损坏不在保修范围内。",
            ),
        ),
        Section(
            "五金件保修",
            (
                f"滑轨、铰链、连接件与升降配件等五金件自签收之日起 {n['hardware_months']} 个月内失效的，可申请保修。",
                "五金件因缺少保养、潮湿环境导致的锈蚀不在保修范围内。",
            ),
        ),
        Section(
            "床垫专项",
            (
                f"床垫弹簧塌陷在 {n['mattress_months']} 个月内可申请检测，按检测结论处理。",
                "床垫污损、烧伤与受潮导致的损坏不在保修范围内。",
            ),
        ),
        Section(
            "保养要求",
            (
                "实木家具需避免长时间日晒与潮湿，建议每半年紧固一次连接件。",
                "软体家具建议定期翻转使用，避免局部长期受压。",
            ),
        ),
        Section(
            "保修流程",
            (
                f"消费者提交订单号与损坏照片后，由售后确认是否上门检测，检测周期为 {n['detect_days']}。",
                "保修不延长原保修期，更换部件沿用原订单的保修截止日期。",
            ),
        ),
        Section(
            "附录：家居保修常见问答",
            (
                f"问题一：沙发框架保修多久？答复：结构件 {n['structure_months']} 个月。",
                f"问题二：滑轨坏了能保修吗？答复：五金件 {n['hardware_months']} 个月内可保修。",
                f"问题三：床垫塌陷保修吗？答复：{n['mattress_months']} 个月内可申请检测。",
                f"问题四：保修检测要等多久？答复：{n['detect_days']}。",
                "问题五：实木家具怎么保养？答复：避免日晒与潮湿，每半年紧固连接件。",
                "问题六：潮湿导致的锈蚀保修吗？答复：不在保修范围内。",
                "问题七：超负荷压坏的结构件保修吗？答复：人为超负荷使用不在保修范围内。",
                "问题八：保修要提供什么？答复：订单号与损坏照片。",
                "问题九：搬家后还能保修吗？答复：可以，保修不因搬迁失效。",
                "问题十：更换的部件保修多久？答复：沿用原订单的保修截止日期。",
                "问题十一：软包污损能保修吗？答复：污损不属于保修范围。",
                "问题十二：保修期内会上门检测吗？答复：由售后确认是否需要上门检测。",
                "问题十三：餐桌腿松了能修吗？答复：结构件保修期内可申请。",
                "问题十四：柜门关不上能保修吗？答复：五金件问题在保修期内可申请。",
            ),
        ),
    ) + _furniture_warranty_annex(n)


_FURNITURE_WARRANTY_OLD_N = dict[str, object](
    structure_months=12,
    hardware_months=6,
    mattress_months=12,
    detect_days="五至七个工作日",
    from_date="2026 年 8 月 1 日",
)
_FURNITURE_WARRANTY_NEW_N = dict[str, object](
    structure_months=24,
    hardware_months=12,
    mattress_months=24,
    detect_days="三至五个工作日",
    from_date="2026 年 10 月 1 日",
)

FURNITURE_WARRANTY_OLD = _doc(
    "furniture-warranty",
    "家居结构保修与保养要求",
    doc_type="warranty",
    version="2026.08.1",
    effective_from=_OLD_FROM,
    effective_to=_TO,
    knowledge_base=KB_CN,
    sections=_furniture_warranty_sections(_FURNITURE_WARRANTY_OLD_N),
)

FURNITURE_WARRANTY_CURRENT = _doc(
    "furniture-warranty",
    "家居结构保修与保养要求",
    doc_type="warranty",
    version="2026.10.1",
    effective_from=_NEW_FROM,
    knowledge_base=KB_CN,
    sections=_furniture_warranty_sections(_FURNITURE_WARRANTY_NEW_N),
)


# ============================================================ 家居发票与价保规则
def _furniture_invoice_price_sections(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "适用范围",
            (
                f"本规则适用于大件家居商品的发票开具与价格保护申请，自 {n['from_date']} 起生效。",
                "通用开票规则以《发票开具与补开规则》为准。",
            ),
        ),
        Section(
            f"{n['pp_days']}日价保",
            (
                f"大件家居商品自订单支付成功之日起 {n['pp_days']} 日内降价的，可申请价格保护。",
                "价保比价以同款同规格的页面标价为准。",
            ),
        ),
        Section(
            "价保条件",
            (
                "申请价保的订单不得已退货或已取消，且需为同款同规格同颜色。",
                "使用优惠券、限时秒杀产生的价差不在价保范围内。",
            ),
        ),
        Section(
            "补开发票",
            (
                f"家居类订单完成后 {n['invoice_days']} 日内可申请补开发票，超期需人工评估。",
                "补开发票金额为订单实付金额，含配送与安装费用。",
            ),
        ),
        Section(
            "配送安装费开票",
            (
                "配送费与安装费包含在实付金额内，按商品明细合并开具。",
                "单独购买安装服务的，按服务项目开具。",
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
            "附录：家居价保常见问答",
            (
                f"问题一：大家具价保多久？答复：{n['pp_days']} 日。",
                f"问题二：价保差额怎么返？答复：以{n['pp_refund']}方式返还。",
                f"问题三：家居订单多久能补开发票？答复：完成后 {n['invoice_days']} 日内。",
                "问题四：安装费能开在发票里吗？答复：包含在实付金额内，按商品明细合并开具。",
                "问题五：单独买的安装服务怎么开票？答复：按服务项目开具。",
                "问题六：价保需要同规格吗？答复：需要同款同规格同颜色。",
                "问题七：大家具降价能价保吗？答复：在价保期内同款同规格降价可申请。",
                "问题八：价保能补几次？答复：次数不限，同一商品仅补偿一次。",
                "问题九：退货后价保补偿怎么办？答复：补偿与实际退款分别计算。",
                "问题十：跨月订单能补票吗？答复：在补开期限内可申请，超期人工评估。",
                "问题十一：运费计入发票金额吗？答复：自营运费包含在实付金额内。",
                "问题十二：电子发票多久开出？答复：参照通用开票规则的时效。",
            ),
        ),
    ) + _furniture_invoice_annex(n)


_FURNITURE_INVOICE_OLD_N = dict[str, object](
    pp_days=3,
    invoice_days=45,
    pp_refund="优惠券",
    from_date="2026 年 8 月 1 日",
)
_FURNITURE_INVOICE_NEW_N = dict[str, object](
    pp_days=7,
    invoice_days=90,
    pp_refund="优惠券或原路退款",
    from_date="2026 年 10 月 1 日",
)

FURNITURE_INVOICE_PRICE_OLD = _doc(
    "furniture-invoice-price",
    "家居发票与价保规则",
    doc_type="invoice",
    version="2026.08.1",
    effective_from=_OLD_FROM,
    effective_to=_TO,
    knowledge_base=KB_CN,
    sections=_furniture_invoice_price_sections(_FURNITURE_INVOICE_OLD_N),
)

FURNITURE_INVOICE_PRICE_CURRENT = _doc(
    "furniture-invoice-price",
    "家居发票与价保规则",
    doc_type="invoice",
    version="2026.10.1",
    effective_from=_NEW_FROM,
    knowledge_base=KB_CN,
    sections=_furniture_invoice_price_sections(_FURNITURE_INVOICE_NEW_N),
)


# ============================================================ 家居送货与安装服务说明
def _furniture_delivery_sections(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "适用范围",
            (
                f"本说明适用于大件家居商品的送货与安装服务，自 {n['from_date']} 起生效。",
                "配送范围与通用时效参照《配送范围与时效》。",
            ),
        ),
        Section(
            "预约时段",
            (
                f"大家具订单在发货前由承运商电话预约上门时间，预约后 {n['lead_days']} 上门送货。",
                f"消费者可在订单详情页备注期望时段，最终以预约电话确认为准。{n['compensation']}",
            ),
        ),
        Section(
            "安装服务",
            (
                "安装服务需在送货时一并预约，安装费按件计收，费用在结算页展示。",
                "安装范围以商品随附说明书列明的项目为准。",
            ),
        ),
        Section(
            "上楼与搬运",
            (
                "无电梯楼层按楼层收取搬运费，具体标准以承运商报价为准。",
                "搬运范围仅限入户，不包括入户内的摆放与组装。",
            ),
        ),
        Section(
            "安装后复紧",
            (
                f"安装完成后 {n['retighten_days']} 内连接件松动可申请免费复紧一次。",
                f"复紧需在安装完成之日起{n['retighten_days']}提出。",
            ),
        ),
        Section(
            "签收与验收",
            (
                "送货当日需当面验收外包装，发现破损应当场拍照并拒收。",
                "安装完成后签收单作为服务完成凭证。",
            ),
        ),
        Section(
            "附录：送装常见问答",
            (
                f"问题一：预约后多久上门送货？答复：{n['lead_days']}。",
                f"问题二：送货晚了有补偿吗？答复：{n['compensation_faq']}",
                "问题三：安装费怎么收？答复：按件计收，结算页展示。",
                "问题四：搬运费怎么算？答复：无电梯楼层按楼层收取。",
                f"问题五：装好后螺丝松了怎么办？答复：{n['retighten_days']}内可免费复紧一次。",
                "问题六：可以自己约时间吗？答复：可在订单备注期望时段，以预约电话确认为准。",
                "问题七：外包装破损怎么办？答复：当场拍照并拒收。",
                "问题八：签收单有什么用？答复：作为安装服务完成的凭证。",
                "问题九：入户摆放另外收费吗？答复：搬运范围仅限入户，不含摆放与组装。",
                "问题十：安装包含哪些项目？答复：以商品说明书列明的项目为准。",
                "问题十一：送装可以分开预约吗？答复：需在送货时一并预约安装。",
                "问题十二：安装费开票吗？答复：包含在实付金额内合并开具。",
            ),
        ),
    ) + _furniture_delivery_annex(n)


_FURNITURE_DELIVERY_OLD_N = dict[str, object](
    lead_days="三个工作日内",
    compensation="",
    compensation_faq="暂无补偿规则",
    retighten_days="一个月内",
    from_date="2026 年 8 月 1 日",
)
_FURNITURE_DELIVERY_NEW_N = dict[str, object](
    lead_days="两个工作日内",
    compensation="超出两个工作日未上门的，订单补偿 20 元优惠券。",
    compensation_faq="超出两个工作日未上门补偿 20 元优惠券",
    retighten_days="十四日内",
    from_date="2026 年 10 月 1 日",
)

FURNITURE_DELIVERY_INSTALL_OLD = _doc(
    "furniture-delivery-install",
    "家居送货与安装服务说明",
    doc_type="policy",
    version="2026.08.1",
    effective_from=_OLD_FROM,
    effective_to=_TO,
    knowledge_base=KB_CN,
    sections=_furniture_delivery_sections(_FURNITURE_DELIVERY_OLD_N),
)

FURNITURE_DELIVERY_INSTALL_CURRENT = _doc(
    "furniture-delivery-install",
    "家居送货与安装服务说明",
    doc_type="policy",
    version="2026.10.1",
    effective_from=_NEW_FROM,
    knowledge_base=KB_CN,
    sections=_furniture_delivery_sections(_FURNITURE_DELIVERY_NEW_N),
)

# ============================================================ 历史版本（2024 / 2025）
# A full four-step version chain per document so "the same question, a
# different answer" is testable at four dates. Adjacent versions always differ
# on at least one number.
_FURNITURE_RETURN_2024_N = dict[str, object](
    window=7,
    quality_window=7,
    pickup_fee="每次取件收取 50 元服务费，费用从退款金额中扣除",
    pickup_faq="每次收取 50 元，从退款中扣除",
    color_rule="主张明显色差需提供同光源对比照片，由售后判定。",
    refund_days="三至十个工作日",
    from_date="2024 年 3 月 1 日",
)
_FURNITURE_RETURN_2025_N = dict[str, object](
    window=7,
    quality_window=10,
    pickup_fee="每次取件收取 50 元服务费，费用从退款金额中扣除",
    pickup_faq="每次收取 50 元，从退款中扣除",
    color_rule="主张明显色差需提供同光源对比照片，由售后判定。",
    refund_days="三至十个工作日",
    from_date="2025 年 3 月 1 日",
)

FURNITURE_RETURN_2024 = _doc(
    "furniture-return-policy",
    "大件家居退换货政策",
    doc_type="policy",
    version="2024.1",
    effective_from="2024-03-01T00:00:00Z",
    effective_to="2025-03-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_furniture_return_sections(_FURNITURE_RETURN_2024_N),
)
FURNITURE_RETURN_2025 = _doc(
    "furniture-return-policy",
    "大件家居退换货政策",
    doc_type="policy",
    version="2025.1",
    effective_from="2025-03-01T00:00:00Z",
    effective_to="2026-08-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_furniture_return_sections(_FURNITURE_RETURN_2025_N),
)

_FURNITURE_WARRANTY_2024_N = dict[str, object](
    structure_months=6,
    hardware_months=3,
    mattress_months=6,
    detect_days="十至十五个工作日",
    from_date="2024 年 3 月 1 日",
)
_FURNITURE_WARRANTY_2025_N = dict[str, object](
    structure_months=12,
    hardware_months=6,
    mattress_months=12,
    detect_days="七至十个工作日",
    from_date="2025 年 3 月 1 日",
)
FURNITURE_WARRANTY_2024 = _doc(
    "furniture-warranty",
    "家居结构保修与保养要求",
    doc_type="warranty",
    version="2024.1",
    effective_from="2024-03-01T00:00:00Z",
    effective_to="2025-03-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_furniture_warranty_sections(_FURNITURE_WARRANTY_2024_N),
)
FURNITURE_WARRANTY_2025 = _doc(
    "furniture-warranty",
    "家居结构保修与保养要求",
    doc_type="warranty",
    version="2025.1",
    effective_from="2025-03-01T00:00:00Z",
    effective_to="2026-08-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_furniture_warranty_sections(_FURNITURE_WARRANTY_2025_N),
)

_FURNITURE_INVOICE_2024_N = dict[str, object](
    pp_days=3,
    invoice_days=30,
    pp_refund="优惠券",
    from_date="2024 年 3 月 1 日",
)
_FURNITURE_INVOICE_2025_N = dict[str, object](
    pp_days=3,
    invoice_days=60,
    pp_refund="优惠券",
    from_date="2025 年 3 月 1 日",
)
FURNITURE_INVOICE_PRICE_2024 = _doc(
    "furniture-invoice-price",
    "家居发票与价保规则",
    doc_type="invoice",
    version="2024.1",
    effective_from="2024-03-01T00:00:00Z",
    effective_to="2025-03-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_furniture_invoice_price_sections(_FURNITURE_INVOICE_2024_N),
)
FURNITURE_INVOICE_PRICE_2025 = _doc(
    "furniture-invoice-price",
    "家居发票与价保规则",
    doc_type="invoice",
    version="2025.1",
    effective_from="2025-03-01T00:00:00Z",
    effective_to="2026-08-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_furniture_invoice_price_sections(_FURNITURE_INVOICE_2025_N),
)

_FURNITURE_DELIVERY_2024_N = dict[str, object](
    lead_days="五个工作日内",
    compensation="",
    compensation_faq="暂无补偿规则",
    retighten_days="三个月内",
    from_date="2024 年 3 月 1 日",
)
_FURNITURE_DELIVERY_2025_N = dict[str, object](
    lead_days="四个工作日内",
    compensation="",
    compensation_faq="暂无补偿规则",
    retighten_days="二个月内",
    from_date="2025 年 3 月 1 日",
)
FURNITURE_DELIVERY_INSTALL_2024 = _doc(
    "furniture-delivery-install",
    "家居送货与安装服务说明",
    doc_type="policy",
    version="2024.1",
    effective_from="2024-03-01T00:00:00Z",
    effective_to="2025-03-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_furniture_delivery_sections(_FURNITURE_DELIVERY_2024_N),
)
FURNITURE_DELIVERY_INSTALL_2025 = _doc(
    "furniture-delivery-install",
    "家居送货与安装服务说明",
    doc_type="policy",
    version="2025.1",
    effective_from="2025-03-01T00:00:00Z",
    effective_to="2026-08-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_furniture_delivery_sections(_FURNITURE_DELIVERY_2025_N),
)

FURNITURE_DOCS: tuple[PolicyDoc, ...] = (
    FURNITURE_RETURN_2024,
    FURNITURE_RETURN_2025,
    FURNITURE_RETURN_OLD,
    FURNITURE_RETURN_CURRENT,
    FURNITURE_WARRANTY_2024,
    FURNITURE_WARRANTY_2025,
    FURNITURE_WARRANTY_OLD,
    FURNITURE_WARRANTY_CURRENT,
    FURNITURE_INVOICE_PRICE_2024,
    FURNITURE_INVOICE_PRICE_2025,
    FURNITURE_INVOICE_PRICE_OLD,
    FURNITURE_INVOICE_PRICE_CURRENT,
    FURNITURE_DELIVERY_INSTALL_2024,
    FURNITURE_DELIVERY_INSTALL_2025,
    FURNITURE_DELIVERY_INSTALL_OLD,
    FURNITURE_DELIVERY_INSTALL_CURRENT,
)
