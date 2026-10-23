"""Stage-17 corpus expansion — apparel (服饰) category documents.

Four synthetic policy documents. Each document is authored **once** as a
parameterised builder: the superseded and the current version are two
instantiations that differ on exactly the numbers the retrieval contract has
to respect (return window, first-return fee relief, warranty months,
price-protection days, invoice window, size-table revision). A query dated
inside the legacy window must cite the legacy version; a later query must cite
the current one.

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
def _apparel_return_annex(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "附录：服饰退换情形速查",
            (
                "情形一：签收第二日申请无理由退货，商品未拆封。结论：符合条件，寄回运费按当前版本规则承担。",
                "情形二：申请退货后超过七日未寄回。结论：申请自动关闭，可在窗口内重新提交。",
                "情形三：仓库验收不通过。结论：会说明原因并寄回商品，可申请复核。",
                "情形四：换货申请通过后同款无库存。结论：可转为退货并按实付金额退款。",
                "情形五：退回商品被判定影响二次销售。结论：可提交照片或视频申请复核。",
                "情形六：套装商品退回其中一件。结论：需整套退回，单独退回按剩余商品重新计价。",
                "情形七：赠品缺失。结论：按赠品标价扣减退款金额。",
                "情形八：退回商品有明显使用痕迹。结论：可能被判定为影响二次销售。",
                "情形九：签收当天发现外包装破损。结论：当场拍照并联系售后，按错发或质量问题处理。",
                "情形十：预售服饰的退换窗口。结论：自实际签收之日起计算。",
                "情形十一：洗后轻微缩水想退。结论：依标洗护后的轻微缩水不属质量问题，按无理由规则判定。",
                "情形十二：错发的尺码。结论：按错发规则处理，不受拆封与窗口限制。",
                "情形十三：个人改码的衣服。结论：修改后的商品不支持无理由退换。",
                "情形十四：换货的价差怎么算。结论：差价部分在下单时以系统计算的金额为准。",
                "情形十五：退换申请被关闭后还能再申请吗。结论：在退换窗口内符合条件可重新提交。",
                "情形十六：超过取件预约时间没来怎么办。结论：联系售后重新预约，长时间未取件的申请可能关闭。",
            ),
        ),
        Section(
            "附录：服饰退换深度问答",
            (
                "问题一：退换申请提交后多久审核？答复：一个工作日内给出审核结论。",
                "问题二：退货物流单号填错怎么办？答复：在售后入口更新物流信息，超时未更新申请可能关闭。",
                "问题三：可以寄到付吗？答复：不支持，需按售后提供的地址寄回并保留单号。",
                "问题四：退款金额和实付不一致怎么查？答复：退款明细列示运费减免与扣减项。",
                "问题五：拒收和退货的区别是什么？答复：拒收在签收前提出，退货在签收后申请。",
                "问题六：取件后商品在运输中损坏怎么办？答复：保留包装与照片，由售后与承运商核查。",
                "问题七：退款是原路返回吗？答复：按原支付渠道退回。",
                "问题八：退货运费险能保服饰吗？答复：寄回运费按本政策执行，不在运费险范围。",
                "问题九：两个订单的服饰能一起寄回吗？答复：需分别提交申请，按订单验收。",
                "问题十：洗后的商品寄回会怎样？答复：可能被判定影响二次销售，验收时说明原因。",
                "问题十一：发票需要随货寄回吗？答复：电子发票无需退回，纸质发票按售后指引处理。",
                "问题十二：换货发出后可以改地址吗？答复：物流发出前可联系售后修改，发出后以物流转寄为准。",
                "问题十三：退换货可以指定快递吗？答复：可以，需保留可追踪的物流单号。",
                "问题十四：寄回商品损坏怎么办？答复：运输风险由寄方承担，建议做好防护。",
                "问题十五：拒收的订单怎么退款？答复：仓库登记拒收，验收通过后按原渠道退款。",
                "问题十六：退换货支持上门取件吗？答复：按通用退货政策的取件方式执行。",
                "问题十七：复核结论多久出？答复：复核由售后人工完成，以工单记录为准。",
                "问题十八：可以只退订单中的部分商品吗？答复：可以，需保持剩余商品可独立计价。",
                f"问题十九：色差争议怎么判定？答复：{n['color_faq']}，争议由售后依同光源对比照与检测结论判定。",
                f"问题二十：运费减免的金额上限是多少？答复：{n['fee_faq']}。",
            ),
        ),
        Section(
            "附录：退换规则边界与例外",
            (
                "边界一：退换窗口的起算日以物流签收记录为准，不以订单完成日计算。",
                "边界二：签收当日与窗口最后一日之间的申请都按窗口内处理。",
                "边界三：换货后新商品的退换窗口按当前版本规则重新判断。",
                "边界四：活动订单的退换窗口不因审核排队而顺延。",
                "边界五：跨境订单的退换适用目的地地区的单独政策。",
                "边界六：页面标注不适用无理由退换的，以页面标注为准。",
                "边界七：争议复核期间不重复发起退款。",
                "边界八：赠品与主商品分属不同仓库时，赠品缺失按标价扣减。",
                "边界九：物流签收记录缺失时，按订单完成日加配送时效推定。",
                "边界十：退换规则以生效日期对应的版本为准。",
            ),
        ),
    )


def _apparel_warranty_annex(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "附录：服饰保修情形速查",
            (
                f"情形一：拉链签收第四个月损坏。结论：五金件保修 {n['hardware_months']} 个月内可申请。",
                f"情形二：外套内衬第三个月开裂。结论：属缝线开裂，{n['seam_months']} 个月内可保修。",
                "情形三：面料起球想保修。结论：起球属正常穿着现象，不在保修范围。",
                "情形四：洗后缩水想保修。结论：依标洗护后的轻微缩水不属保修范围。",
                "情形五：私自改短的裤子脱线。结论：私自修改导致的损坏不在保修范围内。",
                "情形六：外力撕裂。结论：人为损坏不在保修范围内。",
                "情形七：接触染色剂褪色。结论：接触腐蚀性物质导致的损坏不在保修范围内。",
                "情形八：寄修运费谁出。结论：保修范围内由商城承担。",
                "情形九：换货后的新商品保修。结论：沿用原订单的保修截止日期。",
                "情形十：二手购买的服饰。结论：保修不随二手转让转移。",
                "情形十一：改装过的服饰。结论：私自修改导致的损坏不在保修范围内。",
                f"情形十二：保修检测要多久。结论：{n['detect_days']}。",
                "情形十三：没有发票只有订单号。结论：订单号或发票均可作为凭证。",
                "情形十四：面料勾丝。结论：外力导致的勾丝不属于保修范围。",
                "情形十五：五金件生锈。结论：保养不当导致的锈蚀不在保修范围内。",
                "情形十六：缝线补过后又开。结论：同一故障修复后不重复保修，需重新检测确认。",
            ),
        ),
        Section(
            "附录：服饰保修深度问答",
            (
                "问题一：保修申请提交后多久受理？答复：一个工作日内给出受理结论。",
                "问题二：保修和付费维修怎么选？答复：保修期内非人为故障走保修，超期或人为损坏走付费维修。",
                "问题三：保修需要寄回原包装吗？答复：不需要，但需做好运输防护。",
                "问题四：多次故障能反复保修吗？答复：同一故障修复后不重复保修，新故障可再次申请。",
                "问题五：检测结论有异议怎么办？答复：可申请复核，复核结论以工单记录为准。",
                "问题六：五金件和缝线保修期不同怎么判？答复：按各自保修期分别判定。",
                "问题七：保修期内商品可以转让吗？答复：保修服务不随二手转让转移。",
                "问题八：维修更换的部件保修多久？答复：按维修报价单约定，整机保修仍按原订单计算。",
                "问题九：保修期间寄回运费谁出？答复：保修范围内的寄修运费由商城承担。",
                "问题十：人为损坏能付费维修吗？答复：可以，维修前给出报价，确认后开始维修。",
                "问题十一：保修期从哪天起算？答复：自签收之日起计算。",
                "问题十二：无法提供购买凭证怎么办？答复：按支付记录判定是否在保修期内。",
                "问题十三：接触高温导致的损坏保修吗？答复：不在保修范围内。",
                "问题十四：腐蚀性物质导致的褪色保修吗？答复：不在保修范围内。",
                "问题十五：保修能延长吗？答复：保修不延长原保修期，更换部件沿用原订单截止日期。",
                "问题十六：跨境购买的服饰能保修吗？答复：以订单购买地区对应的保修政策为准。",
                "问题十七：商品停产了还能保修吗？答复：以功能等效的配件或方案替代。",
                "问题十八：保修换新和维修怎么选？答复：无法维修时可申请换新，以检测结论为准。",
            ),
        ),
        Section(
            "附录：保修规则边界与例外",
            (
                "边界一：保修期以物流签收记录起算，不以订单完成日起算。",
                "边界二：更换部件沿用原订单的保修截止日期。",
                "边界三：付费维修的报价在维修开始前给出。",
                "边界四：保修范围以本条款为准，聊天描述不构成承诺。",
                "边界五：无法提供凭证时按支付记录判定。",
                "边界六：同一故障修复后不重复保修。",
                "边界七：超出保修期的损坏按付费维修处理。",
                "边界八：保修不因消费者搬迁而失效。",
                "边界九：跨境购买的服饰以购买地区政策为准。",
                "边界十：保修条款以生效日期对应的版本为准。",
            ),
        ),
    )


def _apparel_invoice_annex(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "附录：服饰价保情形速查",
            (
                f"情形一：服饰支付后第四日同款降价。结论：{n['pp_days']} 日价保期内可申请。",
                "情形二：不同尺码可以比价吗。结论：价保需同款同尺码同颜色。",
                "情形三：使用优惠券的价差。结论：不在价保范围内。",
                f"情形四：价保差额怎么返。结论：以{n['pp_refund']}方式返还，优惠券有效期三十天。",
                "情形五：订单已退货还能价保吗。结论：申请价保的订单不得已退货或已取消。",
                f"情形六：服饰订单完成第五十天想补开发票。结论：{n['invoice_days']} 日内可申请补开。",
                "情形七：换货后要重开发票吗。结论：不重新开票，原发票继续有效。",
                "情形八：价保能申请几次。结论：次数不限，同一商品仅补偿一次。",
                "情形九：价保比价含运费吗。结论：不含运费与增值服务。",
                "情形十：跨月订单能补票吗。结论：在补开期限内可申请，超期人工评估。",
                "情形十一：价保补偿的券有效期。结论：三十天。",
                "情形十二：部分退款后还能价保吗。结论：订单未取消且在价保期内可申请。",
                f"情形十三：电子发票多久开出。结论：{n['e_invoice_hours']}。",
                "情形十四：补开发票要什么材料。结论：订单号与开票信息。",
            ),
        ),
        Section(
            "附录：服饰价保深度问答",
            (
                "问题一：价保申请提交后多久出结论？答复：系统自动比价后在一个工作日内给出结论。",
                "问题二：价保补偿可以提现吗？答复：按当前版本的返还方式执行，优惠券形式不可提现。",
                "问题三：多件商品能合并价保吗？答复：按订单内商品分别比价，分别补偿。",
                "问题四：价保比价要同店铺吗？答复：需同一店铺同一商品同一尺码。",
                "问题五：部分退款后还能价保吗？答复：订单未取消且在价保期内可申请。",
                "问题六：价保失败能申诉吗？答复：可提交页面截图申请复核。",
                "问题七：补开发票要什么材料？答复：订单号与开票信息。",
                "问题八：专用发票能补开吗？答复：可申请，需提交企业资质并经审核。",
                "问题九：跨年度发票红冲怎么处理？答复：由财务在申报期内按税务要求处理。",
                "问题十：价保申请能撤销吗？答复：结论出具前可撤销，重新提交需在价保期内。",
                "问题十一：红冲后重开的发票金额怎么算？答复：按实际支付金额重新开具。",
                "问题十二：价保补偿的券能叠加使用吗？答复：按优惠券使用规则执行。",
                "问题十三：订单取消后已开的发票怎么办？答复：需先红冲原发票，再按实际金额处理。",
                "问题十四：补开的发票抬头可以改吗？答复：开票当月可申请换开，跨月需先红冲再重开。",
                "问题十五：电子发票的法律效力？答复：与纸质普通发票具有同等效力。",
                "问题十六：价保比价含赠品价值吗？答复：不含赠品与增值服务。",
                "问题十七：秒杀价能价保吗？答复：限时秒杀产生的价差不在价保范围内。",
                "问题十八：价保补偿的券过期了能补吗？答复：按优惠券规则处理，不在价保范围内。",
            ),
        ),
        Section(
            "附录：价保规则边界与例外",
            (
                "边界一：价保比价以页面标价为准，不含运费与增值服务。",
                "边界二：价保期限自订单支付成功之日起算。",
                "边界三：价保补偿与实际退款分别计算。",
                "边界四：换货不重新开票，原发票继续有效。",
                "边界五：发票红冲需先于重开办理。",
                "边界六：价保认定不因活动叠加而顺延。",
                "边界七：补开期限以当前生效版本为准。",
                "边界八：优惠券、秒杀与会员专享价差不适用价保。",
                "边界九：价保比价需同店铺同款同尺码。",
                "边界十：价保规则以生效日期对应的版本为准。",
            ),
        ),
    )


def _apparel_size_annex(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "附录：尺码情形速查",
            (
                f"情形一：M 码适合什么身材。结论：身高 164 至 168 厘米、胸围 {n['m_bust']} 厘米左右。",
                f"情形二：男装 S 码的胸围。结论：{n['s_bust'] - 4} 厘米左右。",
                "情形三：27 码裤子腰围。结论：67 厘米。",
                "情形四：宽松版型选码。结论：建议选小一码。",
                "情形五：加长版裤长。结论：比常规长 5 厘米。",
                "情形六：修身版型选码。结论：按常穿尺码选择即可。",
                "情形七：页面尺码表错误。结论：按错发规则处理，运费由商城承担。",
                "情形八：两个尺码之间。结论：按版型说明与试穿报告综合判断。",
                "情形九：童装尺码。结论：以商品页标注为准。",
                f"情形十：试穿报告有效期。结论：{n['report_days']} 日。",
                "情形十一：弹力面料缩水。结论：依标洗护下轻微缩水属正常现象。",
                "情形十二：尺码建议不准。结论：个人体型差异按退换货政策执行。",
            ),
        ),
        Section(
            "附录：尺码深度问答",
            (
                f"问题一：S 码适合什么身材？答复：身高 158 至 164 厘米、胸围 {n['s_bust']} 厘米左右。",
                f"问题二：L 码适合什么身材？答复：身高 168 至 172 厘米、胸围 {n['l_bust']} 厘米左右。",
                f"问题三：XL 码适合什么身材？答复：身高 172 厘米以上、胸围 {n['xl_bust']} 厘米左右。",
                f"问题四：男装 M 码的胸围是多少？答复：{n['m_bust'] - 4} 厘米左右。",
                "问题五：男装和女装尺码一样吗？答复：不一样，男装同码胸围建议值少 4 厘米。",
                "问题六：26 码裤子的腰围是多少？答复：64 厘米。",
                "问题七：28 码裤子的腰围是多少？答复：70 厘米。",
                "问题八：修身版型怎么选？答复：按常穿尺码选择即可。",
                "问题九：页面标注版型的以哪个为准？答复：以页面标注为准。",
                "问题十：试穿报告包含哪些内容？答复：身高、体重、常穿尺码与实拍感受。",
                "问题十一：弹力面料选小一码吗？答复：按页面版型说明选择，修身版型按常穿尺码。",
                "问题十二：裤长有几种？答复：常规与加长两种，加长版裤长长 5 厘米。",
                "问题十三：色差和尺码争议都走退换货吗？答复：尺码争议按退换货政策，页面尺码表错误按错发规则。",
                "问题十四：尺码表修订后旧尺码还能用吗？答复：以当前生效版本的尺码对照为准。",
                "问题十五：胸围和身高都要参考吗？答复：两个维度都参考，取覆盖范围更接近的尺码。",
                "问题十六：加大码有对照建议吗？答复：以商品页标注的加大码尺码表为准。",
            ),
        ),
        Section(
            "附录：尺码规则边界与例外",
            (
                "边界一：尺码建议仅供参考，实际版型以商品页展示为准。",
                "边界二：两个尺码之间按版型说明与试穿报告综合判断。",
                "边界三：页面尺码表错误导致的买错按错发规则处理。",
                "边界四：个人体型差异导致的尺码不适按退换货政策执行。",
                "边界五：童装尺码以商品页标注为准。",
                "边界六：加大码以商品页标注的尺码表为准。",
                "边界七：尺码表修订后以当前生效版本为准。",
                "边界八：试穿报告由志愿者填写，仅供参考。",
                "边界九：裤装腰围以厘米数标注，与身高建议相互独立。",
                "边界十：尺码规则以生效日期对应的版本为准。",
            ),
        ),
    )


# ============================================================ 服饰退换货政策
def _apparel_return_sections(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "生效与适用范围",
            (
                f"本政策适用于在中国大陆地区通过 ShopMate 示例商城下单的服饰类商品，"
                f"自 {n['from_date']} 起生效。",
                "服饰类商品包括上装、裤装、裙装、外套与服装配饰；家居、数码等品类适用各自品类的售后政策。",
            ),
        ),
        Section(
            f"{n['window']}日无理由退换",
            (
                f"消费者自签收之日起 {n['window']} 日内，可以在商品完好、吊牌齐全、不影响二次销售的前提下申请无理由退换货。",
                f"因尺码或颜色不适申请的换货同样适用 {n['window']} 日窗口，寄回运费承担方式见运费章节。",
            ),
        ),
        Section(
            "卫生类商品限制",
            (
                "内衣、泳衣、袜子与贴身配饰属于卫生类服饰，拆封或下水后不支持无理由退换。",
                "未拆封且密封包装完好的卫生类服饰，可按无理由退货处理。",
            ),
        ),
        Section(
            "质量问题认定",
            (
                "面料破损、缝线开裂、拉链失效与附件缺失属于质量问题，退换货运费由商城承担。",
                f"页面展示与实物存在轻微色差不属于质量问题，主张明显色差需提供同光源对比照片；{n['color_rule']}",
            ),
        ),
        Section(
            "退换运费承担",
            (
                f"无理由退换货的寄回运费由消费者承担，{n['fee_relief']}",
                "质量问题退换货的往返运费均由商城承担，保价费用不在承担范围内。",
            ),
        ),
        Section(
            "商品状态要求",
            (
                "退回商品需保持清洁、未洗涤、未穿着、未修改，吊牌与原始包装齐全。",
                "存在使用痕迹、污渍、异味或修改痕迹的商品可能被判定为影响二次销售。",
            ),
        ),
        Section(
            "不予退换的情形",
            (
                "定制绣字、个人改码、洗后穿着以及超过退换窗口的订单，不支持无理由退换。",
                "错发、漏发或到货即损坏的服饰不受上述限制，按错发规则处理。",
            ),
        ),
        Section(
            "换货流程与时效",
            (
                f"换货申请审核通过后，消费者寄回商品；仓库签收后 {n['inspect_days']} 完成检验。",
                f"检验通过后 {n['ship_days']} 发出新商品，物流时效参照配送政策执行。",
            ),
        ),
        Section(
            "退款方式",
            (
                "退货商品验收通过后，退款按原支付渠道在一至七个工作日内退回。",
                "换货不产生退款，差价部分在下单时以系统计算的金额为准。",
            ),
        ),
        Section(
            "举证材料",
            (
                "主张质量问题需提供订单号、故障照片或视频，材料不完整时审核暂停。",
                "色差争议需提供同光源下的页面截图与实物对比照。",
            ),
        ),
        Section(
            "附录：常见退换情形速查",
            (
                f"情形一：签收第三天发现拉链失效。结论：属质量问题，{n['window']} 日内可退换，运费由商城承担。",
                f"情形二：签收第十天因尺码不适申请换货。结论：{'仍在' if n['window'] >= 15 else '超出'} {n['window']} 日窗口内，"
                f"{'支持' if n['window'] >= 15 else '不支持'}无理由换货。",
                "情形三：内衣拆封后试穿不合身。结论：卫生类服饰拆封后不支持无理由退换。",
                "情形四：商品与页面色差明显。结论：提供同光源对比照，经确认属于质量问题的可退换。",
                f"情形五：首次退换货的寄回运费。结论：{n['fee_faq']}",
            ),
        ),
    ) + _apparel_return_annex(n)


def _apparel_return_qa(n: dict[str, object]) -> Section:
    entries = (
        f"问题一：服饰退换货的时间窗口是多久？答复：自签收之日起 {n['window']} 日内。",
        f"问题二：无理由退换的寄回运费谁承担？答复：{n['fee_faq']}",
        "问题三：内衣拆封后还能退吗？答复：卫生类服饰拆封后不支持无理由退换，未拆封且密封完好时可退。",
        f"问题四：拉链坏了算质量问题吗？答复：算，属于质量问题，{n['window']} 日内可退换，运费由商城承担。",
        f"问题五：颜色和页面不一样能退吗？答复：{n['color_faq']}",
        f"问题六：换货要多久发出新商品？答复：仓库签收后 {n['inspect_days']} 检验，通过后 {n['ship_days']} 发出。",
        "问题七：退货需要保留吊牌吗？答复：需要，吊牌与原始包装需一并退回。",
        "问题八：洗过的衣服能退吗？答复：已洗涤的商品不支持无理由退换。",
        "问题九：错发的服饰怎么处理？答复：按错发规则处理，不受拆封与窗口限制。",
        "问题十：预售服饰的退换窗口从哪天算？答复：自实际签收之日起计算。",
        "问题十一：定制绣字的衣服能退吗？答复：个人化定制不适用无理由退换。",
        "问题十二：退换货需要提供什么材料？答复：订单号，质量问题需提供照片或视频。",
        "问题十三：部分退货后剩余的商品还能再退吗？答复：在退换窗口内可再次申请。",
        "问题十四：换货和退货可以互相改吗？答复：在审核通过前可联系售后变更处理方式。",
        "问题十五：运费减免后退款怎么算？答复：按实际退款金额计算，减免不计入退款。",
        "问题十六：签收后当天发现破损怎么办？答复：当场拍照并联系售后，按质量问题处理。",
        "问题十七：服饰有色差争议谁判定？答复：由售后依同光源对比照与检测结论判定。",
        "问题十八：超过窗口的质量问题还能处理吗？答复：可按保修政策处理，需提供检测结论。",
    )
    return Section("附录：服饰退换常见问答", entries)


_APPAREL_RETURN_OLD_N = dict[str, object](
    window=7,
    from_date="2026 年 8 月 1 日",
    color_rule="主张明显色差需提供同光源对比照片，由售后判定。",
    fee_relief="商城承担换货发出的运费。",
    fee_faq="寄回运费由消费者承担，商城承担换货发出的运费",
    color_faq="明显色差经确认属于质量问题的可退换",
    inspect_days="三个工作日内",
    ship_days="两个工作日内",
)
_APPAREL_RETURN_NEW_N = dict[str, object](
    window=7,
    from_date="2026 年 10 月 1 日",
    color_rule="色差超出行业公差（色差 ΔE 大于 3.0）时视为质量问题。",
    fee_relief="每笔订单首次无理由退换可减免寄回运费，减免上限为 15 元。",
    fee_faq="每笔订单首次可减免 15 元，之后由消费者承担",
    color_faq="超出行业公差的可按质量问题退换",
    inspect_days="两个工作日内",
    ship_days="一个工作日内",
)

APPAREL_RETURN_OLD = _doc(
    "apparel-return-policy",
    "服饰退换货政策（中国大陆）",
    doc_type="policy",
    version="2026.08.1",
    effective_from=_OLD_FROM,
    effective_to=_TO,
    knowledge_base=KB_CN,
    sections=_apparel_return_sections(_APPAREL_RETURN_OLD_N)
    + (_apparel_return_qa(_APPAREL_RETURN_OLD_N),),
)

APPAREL_RETURN_CURRENT = _doc(
    "apparel-return-policy",
    "服饰退换货政策（中国大陆）",
    doc_type="policy",
    version="2026.10.1",
    effective_from=_NEW_FROM,
    knowledge_base=KB_CN,
    sections=_apparel_return_sections(_APPAREL_RETURN_NEW_N)
    + (_apparel_return_qa(_APPAREL_RETURN_NEW_N),),
)


# ============================================================ 服饰质量保修条款
def _apparel_warranty_sections(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "生效与适用范围",
            (
                f"本条款适用于在中国大陆地区购买的服饰类商品，自 {n['from_date']} 起生效。",
                "保修范围以本条款为准，聊天中的描述不构成保修承诺。",
            ),
        ),
        Section(
            "五金件保修",
            (
                f"拉链、纽扣、按扣与挂钩等五金件自签收之日起 {n['hardware_months']} 个月内出现损坏的，可申请保修。",
                "五金件因外力拉扯、勾挂导致的损坏不在保修范围内。",
            ),
        ),
        Section(
            "缝线保修",
            (
                f"正常穿着情况下缝线开裂的，自签收之日起 {n['seam_months']} 个月内可申请保修。",
                "因尺码不合受力过大或洗涤不当导致的脱线不在保修范围内。",
            ),
        ),
        Section(
            "面料与保养",
            (
                "面料起球、轻微磨损与洗涤后轻微缩水属于正常穿着现象，不属于保修范围。",
                "未按洗护标识洗涤导致的变形、褪色不在保修范围内。",
            ),
        ),
        Section(
            "保修流程",
            (
                f"消费者提交订单号与损坏照片后，由售后确认是否进入检测流程，检测周期为 {n['detect_days']}。",
                "保修不延长原保修期，维修或更换部件沿用原订单的保修截止日期。",
            ),
        ),
        Section(
            "保修凭证",
            (
                "保修以订单号或发票作为购买凭证，转让后的商品不随二手交易转移保修。",
                "无法提供购买凭证时，按支付记录判定是否在保修期内。",
            ),
        ),
        Section(
            "不予保修的情形",
            (
                "人为损坏、外力撕裂、私自修改、接触高温或腐蚀性物质导致的损坏不在保修范围内。",
                "超出保修期后出现的损坏可按付费维修处理，维修前会给出报价。",
            ),
        ),
        Section(
            "附录：服饰保修常见问答",
            (
                f"问题一：拉链坏了保修多久？答复：五金件 {n['hardware_months']} 个月。",
                f"问题二：缝线开裂能保修吗？答复：正常穿着下 {n['seam_months']} 个月内可保修。",
                "问题三：面料起球属于保修范围吗？答复：不属于，起球是正常穿着现象。",
                f"问题四：保修检测要多久？答复：{n['detect_days']}。",
                "问题五：洗后缩水能保修吗？答复：依标洗护后的轻微缩水不属于保修范围。",
                "问题六：保修需要发票吗？答复：订单号或发票均可作为购买凭证。",
                "问题七：二手购买的服饰能保修吗？答复：不能，保修不随二手转让转移。",
                "问题八：扣子掉了能补吗？答复：保修期内可申请，超期可按付费维修处理。",
                "问题九：外套内衬开裂保修吗？答复：属于缝线开裂，在保修期内可申请。",
                "问题十：改装过的服饰还能保修吗？答复：私自修改导致的损坏不在保修范围内。",
                "问题十一：保修期内维修要运费吗？答复：保修范围内的寄修运费由商城承担。",
                "问题十二：换货后的新商品保修怎么算？答复：沿用原订单的保修截止日期。",
                "问题十三：面料勾丝能保修吗？答复：外力导致的勾丝不属于保修范围。",
                "问题十四：配件损坏能单独保修吗？答复：五金件在保修期内可申请。",
            ),
        ),
    ) + _apparel_warranty_annex(n)


_APPAREL_WARRANTY_OLD_N = dict[str, object](
    hardware_months=3,
    seam_months=3,
    detect_days="五至七个工作日",
    from_date="2026 年 8 月 1 日",
)
_APPAREL_WARRANTY_NEW_N = dict[str, object](
    hardware_months=6,
    seam_months=6,
    detect_days="三至五个工作日",
    from_date="2026 年 10 月 1 日",
)

APPAREL_WARRANTY_OLD = _doc(
    "apparel-warranty",
    "服饰质量保修条款",
    doc_type="warranty",
    version="2026.08.1",
    effective_from=_OLD_FROM,
    effective_to=_TO,
    knowledge_base=KB_CN,
    sections=_apparel_warranty_sections(_APPAREL_WARRANTY_OLD_N),
)

APPAREL_WARRANTY_CURRENT = _doc(
    "apparel-warranty",
    "服饰质量保修条款",
    doc_type="warranty",
    version="2026.10.1",
    effective_from=_NEW_FROM,
    knowledge_base=KB_CN,
    sections=_apparel_warranty_sections(_APPAREL_WARRANTY_NEW_N),
)


# ============================================================ 服饰发票与价保规则
def _apparel_invoice_price_sections(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "适用范围",
            (
                f"本规则适用于服饰类商品的发票开具与价格保护申请，自 {n['from_date']} 起生效。",
                "通用开票规则以《发票开具与补开规则》为准，本规则仅补充服饰品类的特殊约定。",
            ),
        ),
        Section(
            f"{n['pp_days']}日价保",
            (
                f"服饰类商品自订单支付成功之日起 {n['pp_days']} 日内，同一商品在同一店铺出现降价时，可申请价格保护。",
                "价保比价以同款同尺码的页面标价为准。",
            ),
        ),
        Section(
            "价保条件",
            (
                "申请价保的订单不得已退货或已取消，且需为同款同尺码同颜色。",
                "使用优惠券、限时秒杀产生的价差不在价保范围内。",
            ),
        ),
        Section(
            "价保方式",
            (
                f"价保差额以{n['pp_refund']}方式返还，优惠券有效期为三十天。",
                "同一订单同一商品仅补偿一次，重复提交会被系统拦截。",
            ),
        ),
        Section(
            "补开发票",
            (
                f"服饰类订单完成后 {n['invoice_days']} 日内可申请补开发票，超期需人工评估。",
                "换货订单不重新开票，原发票继续有效。",
            ),
        ),
        Section(
            "电子发票",
            (
                f"电子普通发票在订单完成后 {n['e_invoice_hours']} 开出，可在订单详情页下载。",
                "发票金额为订单实付金额，优惠券抵扣部分不开票。",
            ),
        ),
        Section(
            "附录：服饰价保常见问答",
            (
                f"问题一：服饰价保期限是多久？答复：{n['pp_days']} 日。",
                f"问题二：价保差额怎么返还？答复：以{n['pp_refund']}方式返还。",
                f"问题三：服饰订单多久能补开发票？答复：完成后 {n['invoice_days']} 日内。",
                f"问题四：电子发票多久开出？答复：订单完成后 {n['e_invoice_hours']}。",
                "问题五：价保可以和退换货同时进行吗？答复：可以，分别计算。",
                "问题六：不同尺码可以比价吗？答复：价保需同款同尺码同颜色。",
                "问题七：优惠券导致的降价能价保吗？答复：不在价保范围内。",
                "问题八：价保能申请几次？答复：次数不限，同一商品仅补偿一次。",
                "问题九：换货后要重开发票吗？答复：不重新开票，原发票继续有效。",
                "问题十：价保补偿的优惠券有效期多久？答复：三十天。",
                "问题十一：部分退款后还能价保吗？答复：订单未取消且在价保期内可申请。",
                "问题十二：价保比价含运费吗？答复：不含运费与增值服务。",
            ),
        ),
    ) + _apparel_invoice_annex(n)


_APPAREL_INVOICE_OLD_N = dict[str, object](
    pp_days=3,
    invoice_days=45,
    e_invoice_hours="三十六小时内",
    pp_refund="优惠券",
    from_date="2026 年 8 月 1 日",
)
_APPAREL_INVOICE_NEW_N = dict[str, object](
    pp_days=7,
    invoice_days=90,
    e_invoice_hours="二十四小时内",
    pp_refund="优惠券或原路退款",
    from_date="2026 年 10 月 1 日",
)

APPAREL_INVOICE_PRICE_OLD = _doc(
    "apparel-invoice-price",
    "服饰发票与价保规则",
    doc_type="invoice",
    version="2026.08.1",
    effective_from=_OLD_FROM,
    effective_to=_TO,
    knowledge_base=KB_CN,
    sections=_apparel_invoice_price_sections(_APPAREL_INVOICE_OLD_N),
)

APPAREL_INVOICE_PRICE_CURRENT = _doc(
    "apparel-invoice-price",
    "服饰发票与价保规则",
    doc_type="invoice",
    version="2026.10.1",
    effective_from=_NEW_FROM,
    knowledge_base=KB_CN,
    sections=_apparel_invoice_price_sections(_APPAREL_INVOICE_NEW_N),
)


# ============================================================ 服饰尺码对照与试穿报告
def _apparel_size_sections(n: dict[str, object]) -> tuple[Section, ...]:
    return (
        Section(
            "适用范围",
            (
                f"本文件给出服饰类商品的尺码对照建议，自 {n['from_date']} 起生效。",
                "尺码建议仅供参考，实际版型以商品页展示为准。",
            ),
        ),
        Section(
            "女装尺码对照",
            (
                f"S 码建议身高 158 至 164 厘米、胸围 {n['s_bust']} 厘米左右；"
                f"M 码建议身高 164 至 168 厘米、胸围 {n['m_bust']} 厘米左右。",
                f"L 码建议身高 168 至 172 厘米、胸围 {n['l_bust']} 厘米左右；"
                f"XL 码建议身高 172 厘米以上、胸围 {n['xl_bust']} 厘米左右。",
            ),
        ),
        Section(
            "男装尺码对照",
            (
                f"S 码建议身高 165 至 170 厘米、胸围 {n['s_bust'] - 4} 厘米左右；"
                f"M 码建议身高 170 至 175 厘米、胸围 {n['m_bust'] - 4} 厘米左右。",
                f"L 码建议身高 175 至 180 厘米、胸围 {n['l_bust'] - 4} 厘米左右；"
                f"XL 码建议身高 180 厘米以上、胸围 {n['xl_bust'] - 4} 厘米左右。",
            ),
        ),
        Section(
            "裤装尺码对照",
            (
                "裤装以腰围厘米数标注，26 码对应腰围 64 厘米，27 码对应 67 厘米，28 码对应 70 厘米。",
                "裤长分为常规与加长两种，加长版裤长长 5 厘米。",
            ),
        ),
        Section(
            "试穿报告",
            (
                f"商品页提供的试穿报告由不同身形的试穿志愿者填写，有效期为 {n['report_days']} 日。",
                "试穿报告包含身高、体重、常穿尺码与实拍感受，仅供参考。",
            ),
        ),
        Section(
            "版型说明",
            (
                "修身版型贴身剪裁，按常穿尺码选择即可；宽松版型偏大，建议选小一码。",
                "页面标注具体版型的商品以标注为准。",
            ),
        ),
        Section(
            "尺码争议处理",
            (
                "因页面尺码表错误导致的尺码不符，按错发规则处理，运费由商城承担。",
                "个人体型差异导致的尺码不适，按退换货政策执行。",
            ),
        ),
        Section(
            "附录：尺码常见问答",
            (
                f"问题一：M 码适合什么身材？答复：身高 164 至 168 厘米、胸围 {n['m_bust']} 厘米左右。",
                "问题二：宽松版型要选小一码吗？答复：建议选小一码。",
                f"问题三：试穿报告有效期多久？答复：{n['report_days']} 日。",
                "问题四：27 码裤子的腰围是多少？答复：67 厘米。",
                "问题五：尺码表错误导致买错怎么办？答复：按错发规则处理，运费由商城承担。",
                "问题六：加长版裤长长多少？答复：比常规长 5 厘米。",
                "问题七：两个尺码之间怎么选？答复：按页面版型说明与试穿报告综合判断。",
                "问题八：童装有尺码表吗？答复：以商品页标注的童装尺码表为准。",
                "问题九：尺码建议不准能退吗？答复：个人体型差异按退换货政策执行。",
                "问题十：弹力面料会缩水吗？答复：依标洗护下轻微缩水属正常现象。",
            ),
        ),
    ) + _apparel_size_annex(n)


_APPAREL_SIZE_OLD_N = dict[str, object](
    s_bust=84,
    m_bust=88,
    l_bust=92,
    xl_bust=96,
    report_days=30,
    from_date="2026 年 8 月 1 日",
)
_APPAREL_SIZE_NEW_N = dict[str, object](
    s_bust=80,
    m_bust=84,
    l_bust=88,
    xl_bust=92,
    report_days=60,
    from_date="2026 年 10 月 1 日",
)

APPAREL_SIZE_GUIDE_OLD = _doc(
    "apparel-size-guide",
    "服饰尺码对照与试穿报告",
    doc_type="policy",
    version="2026.08.1",
    effective_from=_OLD_FROM,
    effective_to=_TO,
    knowledge_base=KB_CN,
    sections=_apparel_size_sections(_APPAREL_SIZE_OLD_N),
)

APPAREL_SIZE_GUIDE_CURRENT = _doc(
    "apparel-size-guide",
    "服饰尺码对照与试穿报告",
    doc_type="policy",
    version="2026.10.1",
    effective_from=_NEW_FROM,
    knowledge_base=KB_CN,
    sections=_apparel_size_sections(_APPAREL_SIZE_NEW_N),
)

# ============================================================ 历史版本（2024 / 2025）
# Each category policy keeps a full version chain so "the same question, a
# different answer" is testable at four dates. Adjacent versions always differ
# on at least one number; the current version differs from every ancestor.
_APPAREL_RETURN_2024_N = dict[str, object](
    window=7,
    from_date="2024 年 3 月 1 日",
    color_rule="主张明显色差需提供同光源对比照片，由售后判定。",
    fee_relief="商城承担换货发出的运费。",
    fee_faq="寄回运费由消费者承担，商城承担换货发出的运费",
    color_faq="明显色差经确认属于质量问题的可退换",
    inspect_days="五个工作日内",
    ship_days="三个工作日内",
)
_APPAREL_RETURN_2025_N = dict[str, object](
    window=7,
    from_date="2025 年 3 月 1 日",
    color_rule="主张明显色差需提供同光源对比照片，由售后判定。",
    fee_relief="每笔订单首次无理由退换可减免寄回运费，减免上限为 10 元。",
    fee_faq="每笔订单首次可减免 10 元，之后由消费者承担",
    color_faq="明显色差经确认属于质量问题的可退换",
    inspect_days="四个工作日内",
    ship_days="两个工作日内",
)

APPAREL_RETURN_2024 = _doc(
    "apparel-return-policy",
    "服饰退换货政策（中国大陆）",
    doc_type="policy",
    version="2024.1",
    effective_from="2024-03-01T00:00:00Z",
    effective_to="2025-03-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_apparel_return_sections(_APPAREL_RETURN_2024_N)
    + (_apparel_return_qa(_APPAREL_RETURN_2024_N),),
)
APPAREL_RETURN_2025 = _doc(
    "apparel-return-policy",
    "服饰退换货政策（中国大陆）",
    doc_type="policy",
    version="2025.1",
    effective_from="2025-03-01T00:00:00Z",
    effective_to="2026-08-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_apparel_return_sections(_APPAREL_RETURN_2025_N)
    + (_apparel_return_qa(_APPAREL_RETURN_2025_N),),
)

_APPAREL_WARRANTY_2024_N = dict[str, object](
    hardware_months=3,
    seam_months=3,
    detect_days="七至十个工作日",
    from_date="2024 年 3 月 1 日",
)
_APPAREL_WARRANTY_2025_N = dict[str, object](
    hardware_months=3,
    seam_months=6,
    detect_days="五至七个工作日",
    from_date="2025 年 3 月 1 日",
)
APPAREL_WARRANTY_2024 = _doc(
    "apparel-warranty",
    "服饰质量保修条款",
    doc_type="warranty",
    version="2024.1",
    effective_from="2024-03-01T00:00:00Z",
    effective_to="2025-03-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_apparel_warranty_sections(_APPAREL_WARRANTY_2024_N),
)
APPAREL_WARRANTY_2025 = _doc(
    "apparel-warranty",
    "服饰质量保修条款",
    doc_type="warranty",
    version="2025.1",
    effective_from="2025-03-01T00:00:00Z",
    effective_to="2026-08-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_apparel_warranty_sections(_APPAREL_WARRANTY_2025_N),
)

_APPAREL_INVOICE_2024_N = dict[str, object](
    pp_days=3,
    invoice_days=30,
    e_invoice_hours="四十八小时内",
    pp_refund="优惠券",
    from_date="2024 年 3 月 1 日",
)
_APPAREL_INVOICE_2025_N = dict[str, object](
    pp_days=3,
    invoice_days=60,
    e_invoice_hours="三十六小时内",
    pp_refund="优惠券",
    from_date="2025 年 3 月 1 日",
)
APPAREL_INVOICE_PRICE_2024 = _doc(
    "apparel-invoice-price",
    "服饰发票与价保规则",
    doc_type="invoice",
    version="2024.1",
    effective_from="2024-03-01T00:00:00Z",
    effective_to="2025-03-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_apparel_invoice_price_sections(_APPAREL_INVOICE_2024_N),
)
APPAREL_INVOICE_PRICE_2025 = _doc(
    "apparel-invoice-price",
    "服饰发票与价保规则",
    doc_type="invoice",
    version="2025.1",
    effective_from="2025-03-01T00:00:00Z",
    effective_to="2026-08-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_apparel_invoice_price_sections(_APPAREL_INVOICE_2025_N),
)

_APPAREL_SIZE_2024_N = dict[str, object](
    s_bust=86,
    m_bust=90,
    l_bust=94,
    xl_bust=98,
    report_days=30,
    from_date="2024 年 3 月 1 日",
)
_APPAREL_SIZE_2025_N = dict[str, object](
    s_bust=84,
    m_bust=88,
    l_bust=92,
    xl_bust=96,
    report_days=45,
    from_date="2025 年 3 月 1 日",
)
APPAREL_SIZE_GUIDE_2024 = _doc(
    "apparel-size-guide",
    "服饰尺码对照与试穿报告",
    doc_type="policy",
    version="2024.1",
    effective_from="2024-03-01T00:00:00Z",
    effective_to="2025-03-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_apparel_size_sections(_APPAREL_SIZE_2024_N),
)
APPAREL_SIZE_GUIDE_2025 = _doc(
    "apparel-size-guide",
    "服饰尺码对照与试穿报告",
    doc_type="policy",
    version="2025.1",
    effective_from="2025-03-01T00:00:00Z",
    effective_to="2026-08-01T00:00:00Z",
    knowledge_base=KB_CN,
    sections=_apparel_size_sections(_APPAREL_SIZE_2025_N),
)

APPAREL_DOCS: tuple[PolicyDoc, ...] = (
    APPAREL_RETURN_2024,
    APPAREL_RETURN_2025,
    APPAREL_RETURN_OLD,
    APPAREL_RETURN_CURRENT,
    APPAREL_WARRANTY_2024,
    APPAREL_WARRANTY_2025,
    APPAREL_WARRANTY_OLD,
    APPAREL_WARRANTY_CURRENT,
    APPAREL_INVOICE_PRICE_2024,
    APPAREL_INVOICE_PRICE_2025,
    APPAREL_INVOICE_PRICE_OLD,
    APPAREL_INVOICE_PRICE_CURRENT,
    APPAREL_SIZE_GUIDE_2024,
    APPAREL_SIZE_GUIDE_2025,
    APPAREL_SIZE_GUIDE_OLD,
    APPAREL_SIZE_GUIDE_CURRENT,
)
