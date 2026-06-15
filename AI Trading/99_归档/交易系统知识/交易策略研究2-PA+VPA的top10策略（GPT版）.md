# 四类核心高流动性市场中的 PA 与 VPA 共振开仓扳机深度研报

## 研究结论摘要

如果把“价格行为 + 量价共振”严格限定为**几何结构必须成立、且成交量异常必须独立验证**，那么公开文献、官方市场结构资料与微观结构研究共同支持的结论非常清晰：**真正可迁移的优势，不在裸 K 线，而在“流动性位置 + 异常成交活跃度 + 订单流/量价失衡后的结构确认”**。纯粹蜡烛图在传统股票样本里长期并不稳健，且对数据窥探与交易成本极其敏感；相反，订单流失衡、止损级联、异常成交活跃度、以及高量却低位移的“吸收/努力—结果背离”更接近市场实际的供需传导机制。citeturn24view0turn34search0turn22view5turn22view3turn36view0

在四个目标市场里，**NQ 的 VPA 信号质量最高**，原因不是它“最会走形态”，而是它由 CME Globex 的中央限价订单簿撮合，真实成交量与订单簿深度都可观测；**BTC 与 ETH 次之**，但前提是只用优质现货/永续合约场所并过滤洗售体量，否则 RVOL 与“放量假突破”会被脏数据破坏；**XAUUSD 最弱，但不是无效**，而是必须把“量”重新解释为**同一经纪商、同一会话、同一分钟桶中的 tick 活跃度异常**，不能把它当成真实名义成交量。citeturn35view8turn35view9turn21view8turn21view0turn21view1turn22view15turn35view5turn35view6turn35view7turn22view8turn22view9

基于这些约束，本报告给出的 Top 10 扳机并不是“最常见”的形态，而是**在四类市场里最符合机构参与、最能被算法严格表达、且跨资产可移植性最高**的一组模板。综合排序的核心倾向是：**假突破回收、停止量后的缩量测试、以及高量窄实体吸收**，优先级明显高于单纯突破、裸 Pin Bar 或离散的单根反转 K。citeturn36view0turn22view7turn22view6turn22view5turn22view17turn22view18

## 核心市场的量价微观结构差异

四类市场最大的差异，不是波动率，而是**你手里拿到的“量”到底是什么**。BTC 与 ETH 的可用量通常来自交易所 K 线字段、逐笔成交、以及永续合约的 taker buy/sell 统计；交易所官方接口明确区分了基准币成交量、报价币成交量、成交笔数以及 taker 主动买量，因此加密市场可以做到比传统 OTC 外汇更细致的“方向化量能”分析。问题在于，加密市场是**碎片化且质量不均**的，NBER 的洗售交易研究发现，不受监管的交易所会在首位数字分布、尾部分布和整数化交易尺寸上呈现异常模式，这意味着**未过滤 venue 的 RVOL 往往没有统计学意义**。citeturn21view0turn21view1turn22view15turn22view12turn22view13turn22view16

黄金现货则完全不同。全球黄金本身非常深，世界黄金协会统计显示，黄金在 OTC、期货与 ETF 等多个场所的总成交非常可观，LBMA 也持续推进 OTC 交易报告透明化；但零售交易者在 XAUUSD 上最常见到的并不是 LBMA 或 COMEX 的真实合并成交量，而是交易平台上的 **tick volume**。MetaTrader 官方文档明确写明：在外汇市场里，volume 指的是**时间区间内的价格变动 tick 数**，而不是成交手数；历史研究确实证明，tick 频次与真实成交量存在较强相关，但这种关系会随时期与样本变化而不稳定。因此，黄金的 VPA 只能把“量”解释为**活跃度代理**，而不能把 `2 倍均量` 直接当成 `2 倍真实成交`。citeturn21view10turn21view9turn35view2turn35view3turn35view4turn35view5turn35view6turn35view7turn22view8turn22view9

NQ 的情况最干净。CME Globex 把买卖兴趣汇总到中央限价订单簿，市场深度、活跃合约成交量和盘口都来自统一撮合环境；这意味着 NQ 的 VPA 可以直接建立在**真实合约成交量 + 盘口深度/订单簿再补充**的框架上，而不是代理变量。对同一类“高量窄实体吸收”或“放量假突破回收”，NQ 的统计稳定性通常会高于 XAUUSD，也通常高于未清洗的 BTC/ETH 聚合量。citeturn35view8turn35view9turn21view4turn21view8

这直接决定了跨资产 RVOL 的正确写法：**绝不能比较原始量值，只能比较“同资产、同 venue、同会话、同时间桶、同状态桶”下的异常程度**。学术上，交易活动存在显著的日内季节性；Sancetta 指出，交易到达率的预期分布本身就是高频执行算法的重要输入，且会在开盘、收盘和公告时点发生尖峰；比特币的日内成交与波动也与欧美股市交易时段重叠部分显著增强；外汇的日内活动在东京与伦敦时段呈明显 U 型。换言之，RVOL 的基准不能是“过去 20 根均量”，而应是“过去若干日、同一分钟桶、同星期几、同波动状态”的条件中位数或稳健均值。citeturn25view0turn22view10turn28search1turn22view20

可执行的统一基准可以写成下面这样，其中 `Vol` 在 NQ 是真实成交量，在 BTC/ETH 优先用**报价币名义成交量**或高质量永续合约 notional volume，在 XAUUSD 则是同一经纪商 feed 的 tick volume：

```text
RVOL*_t = Vol_t / Median(Vol | asset, venue, same_TOD_bucket, same_DOW, last_N_sessions)

VZ*_t = (log(1 + Vol_t) - Median(log(1+Vol) | same bucket))
        / (1.4826 * MAD(log(1+Vol) | same bucket))
```

如果再进一步考虑深度与冲击，FX 研究表明，交易量对应的价格冲击与市场深度成反比，且在不确定性上升时会扩大；因此跨资产应用时，**同样的 RVOL 阈值还要再按最近的实现波动率状态做二次分层**。直白地说，在 CPI/NFP 或 FOMC 这种时段，`RVOL = 2` 不等于“异常”，它可能只是“正常新闻流量”。citeturn23view4turn22view4turn25view0

## 统一算法框架与排序方法

本报告不把“胜率”定义为模糊的方向正确，而统一定义为：**触发入场后，价格先到达 `+1R` 目标且尚未先触及结构止损**。这是一个偏执行端的定义，因为不同扳机的核心价值不在长期持有，而在于它能否在机构流动性转移的最初阶段，给出**有条件优势**。以下 Top 10 的“预估胜率”并非任何单篇论文直接给出的原始表格，而是依据**市场结构可靠性、异常量研究、订单流文献、以及多市场日内特征**做出的研究合成估计。之所以采用合成法，是因为公开世界里并不存在一份对 BTC、ETH、XAUUSD tick feed 与 NQ 真量，在同一手续费和同一时间桶框架下联合回测这十类 Wyckoff/VPA 模板的标准化数据库。对技术规则本身，学界也反复警告必须处理数据窥探与交易成本。citeturn34search0turn24view0turn34search4turn34search6

算法上，本文把所有扳机都拆成两个层级。第一个层级是**价格几何层**，只处理 K 线几何与结构位置；第二个层级是**量价验证层**，只处理活跃度异常、主动成交方向、以及努力—结果失衡。没有通过几何层，直接忽略；没有通过量价层，信号降级为观察而不是执行。这样做的原因很简单：裸 K 线没有足够的微观结构信息，而订单流失衡与止损级联才是真正驱动短中期位移的变量。citeturn24view2turn22view5turn22view3turn36view0

统一使用的基础量化变量如下：

```text
TR_t            = High_t - Low_t
Body_t          = abs(Close_t - Open_t)
UpperWick_t     = High_t - max(Open_t, Close_t)
LowerWick_t     = min(Open_t, Close_t) - Low_t
BodyToRange_t   = Body_t / TR_t
TailLowRatio_t  = LowerWick_t / TR_t
TailHighRatio_t = UpperWick_t / TR_t
CloseLoc_t      = (Close_t - Low_t) / TR_t
ATR_t           = ATR(20)
RangeNorm_t     = TR_t / ATR_t
RVOL*_t         = 条件相对量
VZ*_t           = 条件稳健量能 Z 分数
ERDiv_t         = VZ*_t - Zscore(RangeNorm_t)
```

对 BTC 与 ETH，再增加方向化成交代理：

```text
TakerImb_t = (2 * TakerBuyQuoteVolume_t - QuoteVolume_t) / QuoteVolume_t
```

这一步是加密市场相对外汇/黄金的制度优势，因为交易所会直接给出 taker buy/sell 量。citeturn21view0turn21view1

综合排序分数不是“谁看起来最漂亮”，而是五项加权：**微观结构扎实度、量能异常辨识度、跨资产可移植性、数据源稳健性、执行清晰度**。在这个框架下，**假突破回收**和**停止量后的缩量测试**长期排名靠前，因为它们同时满足：一，直接对应止损级联与供给/需求抽干；二，能用严格几何与量能门槛表达；三，在 NQ、加密与 XAUUSD 里都存在相同的供需语义，只是量的定义不同。citeturn36view0turn22view7turn22view5turn22view6

## 扳机库总表

| 排名 | 扳机名称 | 核心定义 | 典型频度 | 综合分 | 最强资产顺序 |
|---|---|---|---|---:|---|
| 1 | 爆量扫损回收 | 外部流动性被扫后，长尾回收并伴随异常量 | 中 | 92 | NQ ≈ BTC > ETH > XAU |
| 2 | 停止量后的缩量测试 | 前置停止量后，回踩无量确认供给/需求已枯竭 | 低到中 | 90 | NQ > BTC > ETH > XAU |
| 3 | 高量窄实体吸收 | 高量但位移有限，关键位吸收主动单 | 中 | 88 | NQ > BTC ≈ ETH > XAU |
| 4 | 放量突破与缩量回踩续攻 | 真突破发生在量能扩张，回踩时量能收缩 | 中 | 86 | NQ > BTC > ETH > XAU |
| 5 | 努力与结果背离失败突破 | 大量成交却推不动价格，随后回落/回升失败 | 中 | 84 | NQ ≈ BTC > ETH > XAU |
| 6 | 无供给与无需求测试 | 趋势中继中的窄幅低量回撤/反抽 | 高 | 82 | NQ > BTC ≈ ETH > XAU |
| 7 | 开盘或会话极值放量拒绝 | 主时段极值假突破，异常量后回到区间内 | 中 | 80 | NQ > XAU > BTC > ETH |
| 8 | 缩量压缩后的真实扩张 | 波动与量同步枯竭，随后被异常量点火 | 中 | 78 | BTC > ETH ≈ NQ > XAU |
| 9 | 停止量关键反转棒 | 终局性高量反转 K，随后被确认 | 低 | 76 | NQ > BTC > ETH > XAU |
| 10 | 二次推进衰竭与反向高潮量 | 第二/第三推结果衰减，反向量高潮收尾 | 低 | 74 | NQ ≈ BTC > ETH > XAU |

上表的综合分与资产顺序为**研究合成结果**，不是任何单篇论文的原始输出。它们建立在以下共识之上：纯蜡烛图边际价值弱且易受数据窥探影响；可迁移优势主要来自订单流失衡、止损级联、异常量与日内结构季节性；NQ 的量最真实，BTC/ETH 必须过滤可疑 venue，XAUUSD 的“量”只能做经纪商内 tick 活跃度异常。citeturn24view0turn34search0turn22view5turn36view0turn22view15turn35view5turn35view6turn35view7turn35view8

## 扳机逐项解析

下列所有定义默认先给**多头版本**，空头完全镜像处理。所有“预估胜率”均为研究合成估计，统一以“先到 1R 未先打止损”为口径。

**第 1 名｜爆量扫损回收**

**资金逻辑。** 这是最典型的 Spring / Upthrust After Distribution 版本。先利用关键高点/低点外侧的止损堆积触发正反馈订单，再由更大的被动流动性完成吸收；一旦收盘重新站回原区间，说明突破流量已经被吃掉，市场从“追价成交”切回“被吸收后的再定价”。止损订单会引发价格级联，这一点在 FX 文献中有直接证据；订单簿研究也表明，价格在短窗口里主要由供需失衡驱动，而大单后能否迅速补回深度，决定了这类假突破究竟会延续还是反噬。citeturn36view0turn22view5turn22view6

**算法定义。**
```text
Context:
  价格触及外部流动性池（前高/前低、前日高低、会话极值）

Bull Trigger:
  Low_t < SwingLow_{n}
  Close_t > SwingLow_{n}
  TailLowRatio_t >= 0.55
  BodyToRange_t <= 0.45
  CloseLoc_t >= 0.65
  (VZ*_t >= 2.0 OR RVOL*_t >= 2.2)

Extra:
  BTC/ETH: TakerImb_t > +0.10
  XAUUSD: 同一 broker feed 的 tick VZ* >= 1.8
```

**跨资产统计。** 研究合成估计下，条件胜率大致为：BTC `57%–61%`，ETH `56%–60%`，XAUUSD `53%–57%`，NQ `58%–62%`。最优上下文不是“任意前高前低”，而是**会话极值、前日高低、公告后第一轮过冲、以及衍生品主导的流动性节点**。BTC 与 ETH 因为期货/永续在价格发现中可领先现货，所以用优质永续合约的 taker 量来确认 sweep 会明显优于只看现货；NQ 则最适合放在 RTH 开盘或宏观数据时段；XAUUSD 最好放在伦敦—纽约重叠交易窗口。citeturn22view12turn22view13turn22view16turn22view17turn22view18turn22view10turn28search1

**异构风控。** 标准止损放在 sweep 极值下方 `max(0.12*ATR20, 0.25*TR_t)` 的缓冲区。更激进的做法，是若下一根 K 线重新收回 sweep 外侧，直接判为失败；若三根 K 内没有离开原区间中轴，也应时间止损，因为真正的强回收不应该长时间滞留在被扫区外侧。citeturn22view6turn22view5

**动态出场。**
```text
if long_position:
    if opposite_bar.VZ* >= 2.5 and opposite_bar.CloseLoc <= 0.35:
        exit_all()    # 反向异常量高潮
    elif new_high and ERDiv_t >= 1.5:
        take_partial(0.5)   # 努力大、结果差
    elif bars_since_entry >= 6 and max_favorable_excursion < 0.6R:
        exit_all()    # 回收失去加速度
```

**第 2 名｜停止量后的缩量测试**

**资金逻辑。** 这不是第一脚反转，而是第一脚之后最干净的二次确认。停止量说明大资金已经入场吸收；随后价格回到测试位，如果成交活跃度显著衰减，却再也打不穿前低/前高，意味着浮动供给已经枯竭，测试通过。威科夫框架里，这是最接近“真正无供给/无需求”的确认环节，因此频率低于扫损回收，但条件优势常更高。高量/高潮本身对未来回报具有信息含量，而“缩量测试”正是对这份信息做二次筛选。citeturn26search7turn26search6turn22view7

**算法定义。**
```text
Precondition:
  在过去 m 根内出现 Stopping Volume Bar:
      VZ* >= 2.2
      RangeNorm >= 1.4
      CloseLoc >= 0.35  (多头版)

Test Trigger:
  价格回踩停止量 K 的下半区或其低点上方
  RVOL*_test <= 0.70
  RangeNorm_test <= 0.75
  Close_test > Mid(StoppingBar)
  Low_test >= Low_stopping - 0.10*ATR20
```

**跨资产统计。** 研究合成估计：BTC `58%–62%`，ETH `57%–61%`，XAUUSD `55%–59%`，NQ `60%–64%`。这类扳机对**位置**的依赖极高，必须出现在停止量之后，而不是普通回调中。最优上下文包括：扫损回收后的第一次回踩、宏观数据尖峰后的二次回访、以及明显 balance 区底部/顶部的再测试。NQ 因真实量能与开盘后价差结构更利于识别“测试是否无量”，通常最稳定；XAUUSD 也能做，但只能用同 broker tick feed 内部标准化。citeturn22view17turn22view18turn35view5turn35view7turn22view8turn22view9

**异构风控。** 入场后硬止损放在测试低点下方 `0.08–0.12 ATR`；如果要提高容错，可放到前置停止量 K 的极值之外。若测试后下一根 K 出现中等以上 `RVOL* > 1.2` 的顺势确认，止损可上移到测试 K 下方；若测试后竟然放量跌穿/涨穿测试边界，则不是“测试失败”，而是“吸收失败”，必须立刻离场。citeturn22view6turn22view5

**动态出场。**
```text
if long_position:
    if impulse_leg_completed and opposite_bar.VZ* >= 2.2 and Close < prior_bar_mid:
        exit_all()
    elif price_reaches_2R and subsequent_test.RVOL* <= 0.6:
        trail_below_test_low()
```

**第 3 名｜高量窄实体吸收**

**资金逻辑。** 这类形态的本质是：**有很多成交，但价格不怎么走**。在微观结构语言里，这意味着主动打进来的流量，被关键价位附近的被动深度持续吸收。它通常不是单根 K，而是一个小簇形态：多根窄实体、极小位移，同时伴随持续高量。它最接近“隐藏大单护盘/压盘”的盘面足迹。订单簿研究显示，短窗口价格变化由供需失衡驱动，而大量交易后若订单簿能快速回补、价格却不扩展，就是典型的吸收与补深度现象。citeturn22view5turn22view6

**算法定义。**
```text
Window = last 3 to 5 bars
At Key Level:
  mean(BodyToRange) <= 0.35
  count(VZ* >= 1.5) >= 2
  max(abs(Close_i - Close_{i-1})) <= 0.25 * ATR20
  touch_count(level) >= 2

Entry:
  发生离开吸收簇的确认 K
  Close_confirm > cluster_high      # 多头
  RVOL*_confirm >= 1.2
```

**跨资产统计。** 研究合成估计：BTC `55%–59%`，ETH `54%–58%`，XAUUSD `53%–57%`，NQ `57%–61%`。上下文只允许出现在**关键水平附近**，例如前日价值边界、前高前低、开盘区间边缘，或长期 balance 的顶部/底部。它在 NQ 上尤为干净，因为订单簿与真实成交量都更完整；在 BTC/ETH 上也强，但要尽量用单 Venue 高质量永续或高质量聚合，而不是全网混合脏量。citeturn35view8turn21view8turn22view15turn23view0

**异构风控。** 止损放在吸收簇最外侧 `0.10 ATR` 之外。若突破吸收簇后，价格立刻回到簇内并停留超过两根 K，说明这不是吸收完成而是**库存对敲后的未完成分配/吸筹**，应主动砍掉。citeturn22view6

**动态出场。**
```text
if breakout_from_cluster:
    if breakout_bar_followthrough_absent for 2 bars:
        exit_all()
    if opposite_climax.VZ* >= 2.0:
        exit_all()
    if distance_from_cluster >= 1.5R:
        trail_on_bar_lows()
```

**第 4 名｜放量突破与缩量回踩续攻**

**资金逻辑。** 真突破不是“穿过去”而已，而是**穿过去时必须有量、回踩时必须没量、重新启动时再次放量**。这本质上是“主动需求先占领价格，再确认对手盘没有跟进”的三段式结构。若回踩仍带着高量，那通常不是健康续攻，而是上方/下方仍有大量对手盘未消化。citeturn22view5turn23view4turn25view0

**算法定义。**
```text
Breakout Bar:
  Close_t > level
  CloseLoc_t >= 0.80
  RangeNorm_t >= 1.1
  RVOL*_t >= 1.8

Pullback:
  next 1~4 bars max(RVOL*) <= 0.85
  retrace <= 0.50 * breakout_range
  close remains above breakout midpoint

Re-Trigger:
  reversal_bar closes back in breakout direction
  RVOL* >= 1.2
  BTC/ETH: TakerImb confirms direction
```

**跨资产统计。** 研究合成估计：BTC `56%–60%`，ETH `55%–59%`，XAUUSD `52%–56%`，NQ `58%–61%`。最好的环境是**已经平衡足够久**、且之前有明显量收缩；如果在单边趋势末端才出现这种“突破”，就会迅速退化成第 5 名那种失败突破。NQ 和 BTC 通常表现更好：前者因为真量，后者因为衍生品驱动的价格发现和 24/7 压缩—扩张节奏更连续。citeturn22view12turn22view13turn33view0turn22view10turn22view20

**异构风控。** 止损放在 pullback 低点之外 `0.10 ATR`。若回踩过程中的 `RVOL*` 意外升高到 `>1.2`，应当立即把信号从“续攻”降级为“尚未确认”，不再机械挂单。citeturn23view4turn25view0

**动态出场。**
```text
if continuation_long:
    if successively_higher_highs and last_bar.VZ* >= 2.2 and CloseLoc < 0.55:
        take_partial()
    if breakout_level_lost_on_above_avg_volume:
        exit_all()
```

**第 5 名｜努力与结果背离失败突破**

**资金逻辑。** 这是“高量却走不动”的反向运用。若价格打到关键位附近出现异常高量，但穿越后的净位移极小、收盘位置又不强，说明主动流量正在被对手方吸收，所谓突破只是“成交很多”，不是“价格接受”。这与 Cont 的 OFI 观点相容：真正推动价格的是失衡本身，而不是机械的成交笔数；若有量无位移，那是吸收，不是共识。citeturn22view5turn22view6

**算法定义。**
```text
Failed Breakout:
  VZ*_t >= 2.0
  RangeNorm_t <= 0.90    or
  NetBreakDistance <= 0.15 * ATR20
  Close_back_inside_range within 1 bar
  ERDiv_t >= 1.2         # 量异常 > 位移异常
```

**跨资产统计。** 研究合成估计：BTC `56%–59%`，ETH `55%–58%`，XAUUSD `52%–55%`，NQ `57%–60%`。最佳上下文是**成熟趋势末端、第三次冲击、整数位、前高前低、或会话极值**。对 NQ 和 BTC 来说，这种模式非常常见，因为两者都容易在显眼关口吸引追单；对 XAUUSD 而言，问题不是模式不存在，而是 tick volume 的大小受 feed 影响更大，所以阈值必须更稳健。citeturn22view17turn22view18turn35view5turn35view7turn36view0

**异构风控。** 失败突破的硬止损必须放在失败 K 的极值外，不要放在突破水平内侧，因为真正的失败突破常会再试探一次。若重试时 `RVOL*` 比第一次更低，仓位可加；若重试时 `RVOL*` 更高且净位移改善，则原假设失效，立即离场。citeturn22view6

**动态出场。**
```text
if fade_position:
    if opposite_test_on_low_volume succeeds:
        hold_runner()
    if counter_bar.VZ* >= 2.3 and reclaims failed_level:
        exit_all()
```

**第 6 名｜无供给与无需求测试**

**资金逻辑。** 这是趋势中继最干净的版本。前提是趋势已经建立；随后出现一根或一组**窄幅、低量、反方向推进乏力**的回撤 K，说明对手盘意愿极低。它不是反转模型，而是趋势内“对手盘缺席”的执行模型。技术规则文献中，短期规则的有效性常常来自短期动量本身，而这种信号正是把短期动量与量能缺失绑定。citeturn34search3turn22view20

**算法定义。**
```text
Trend Filter:
  HH-HL structure intact
  or price above anchored VWAP / trend pivot

Signal Bar:
  RVOL* <= 0.65
  RangeNorm <= 0.60
  BodyToRange <= 0.45
  CloseLoc >= 0.60     # 多头回撤后收在上半区
```

**跨资产统计。** 研究合成估计：BTC `55%–59%`，ETH `54%–58%`，XAUUSD `52%–56%`，NQ `56%–60%`。它的频率高于前几名，但单笔优势略低，因此更适合**组合化执行**。上下文必须是明确的已建立趋势、完整的第一次推进、以及回撤进入原始突破区或效率缺口边缘时；若没有明确的先导推动，这类“低量小 K”只会沦为噪音。citeturn22view20turn25view0

**异构风控。** 止损压在信号 K 的低点之外即可，因为这类扳机追求的是低风险中继。时间止损尤其重要：若三根 K 内没有恢复趋势方向的量能扩张，应主动减仓。citeturn25view0

**动态出场。**
```text
if continuation_trade:
    if first_counter_bar.VZ* >= 2.0 and closes_through_signal_mid:
        exit_all()
    elif trend_persists:
        trail_below_last_low_volume_test()
```

**第 7 名｜开盘或会话极值放量拒绝**

**资金逻辑。** 主时段开盘时，信息、对冲、再平衡、止损和开仓需求共同堆叠，最容易出现“先过冲、后纠偏”。美国股指期货的开盘大波动后反转有长期证据；外汇与黄金在主会话切换时，活动与波动也显著上升。因此，**开盘区间外侧的假突破 + 异常量 + 收回区间**，比普通时间的同形态更有统计价值。citeturn22view17turn22view18turn28search1turn22view10turn22view20

**算法定义。**
```text
Session Window:
  NQ: RTH first 30-60 min
  XAU: London/NY overlap
  BTC/ETH: 欧/美重叠活跃时段

Trigger:
  break session_high/session_low by <= 0.35*ATR20
  close back inside opening/session range
  TailRatio >= 0.50
  RVOL* >= 2.0
```

**跨资产统计。** 研究合成估计：BTC `55%–58%`，ETH `54%–57%`，XAUUSD `55%–58%`，NQ `58%–61%`。这是少数 XAUUSD 不明显劣于 BTC/ETH 的场景，因为黄金的交投明显受伦敦和纽约时段支配，而加密市场虽然 24/7，但其成交和波动仍与欧美股市活跃时段重叠增强。citeturn22view10turn28search1turn22view17turn22view18

**异构风控。** 止损只放极值外侧，不要放开盘区间边界，因为开盘假突破常伴随第二次探测。若发生第二次探测且量显著缩小，可加分；若第二次探测量更大且直接站稳，则说明是趋势日而不是均值回复日。citeturn22view17turn22view18

**动态出场。**
```text
if session_reversal:
    if VWAP_reached and opposite_climax.VZ* >= 2.0:
        take_profit()
    elif session_range_reentered_but_no_extension within 4 bars:
        exit_all()
```

**第 8 名｜缩量压缩后的真实扩张**

**资金逻辑。** 与其追裸突破，不如等待“波动与量同步枯竭”后的真实点火。Sancetta 的研究强调，交易到达率存在显著季节性尖峰，公告与开收盘会打断平稳状态；因此最好的扩张，不是常态大 K，而是**前面先出现可测的干涸，随后才出现异常量扩张**。这种结构在 BTC/ETH 上尤其好用，因为 24/7 环境允许更连续的压缩—释放过程。citeturn25view0turn22view10turn22view20

**算法定义。**
```text
Compression:
  mean(RangeNorm, last m bars) <= 0.75
  mean(RVOL*, last m bars) <= 0.75
  max(high) - min(low) <= 1.5 * ATR20

Expansion Trigger:
  close outside compression box
  RangeNorm_t >= 1.2
  RVOL*_t >= 1.8
  hold above breakout midpoint on next bar
```

**跨资产统计。** 研究合成估计：BTC `56%–60%`，ETH `55%–59%`，XAUUSD `51%–55%`，NQ `55%–58%`。BTC/ETH 稍占优，是因为它们的波动聚类更连续、且衍生品主导的短期价格发现会把压缩后的释放演绎得更极端；NQ 次之；XAUUSD 因 tick-volume 代理噪音较高，必须更强调收盘位置和后续保持，而不是只看首发大 K。citeturn33view0turn22view13turn22view12

**异构风控。** 初始止损放在压缩盒另一侧。若突破后下一根 K 直接把突破 K 的一半以上吞回，且量没有继续放大，则把信号取消。citeturn25view0

**动态出场。**
```text
if breakout_from_compression:
    if second_expansion_bar.VZ* >= 2.2 and CloseLoc < 0.55:
        take_partial()   # 可能进入买高潮
    if close_back_inside_box:
        exit_all()
```

**第 9 名｜停止量关键反转棒**

**资金逻辑。** 这是一种“单根 K 浓缩版的终局反转”：极端高量、显著宽幅，但收盘明显偏离最坏位置。其意义不在于蜡烛名称，而在于**恐慌释放之后，主动打单已被逆向吸收**。大波动和异常成交量往往伴随短期过度反应，股指期货开盘大波动后的反转尤有证据；停止量反转棒就是这种过度反应在单根 K 上的高度压缩版本。citeturn22view17turn22view18turn26search6turn26search7

**算法定义。**
```text
Stopping Bar (bullish):
  Close < Open
  RangeNorm >= 1.4
  VZ* >= 2.2
  CloseLoc >= 0.35
Confirmation:
  next bar closes above stopping_bar_mid
  RVOL*_confirm >= 0.9
```

**跨资产统计。** 研究合成估计：BTC `54%–57%`，ETH `53%–56%`，XAUUSD `52%–55%`，NQ `55%–58%`。它不如第 1 名可靠，因为**没有显式 sweep 与回收条件**，因此更容易把“普通大波动”误判成停止量。但若出现在周线/日线关键位、前日低点附近、或会话极值处，信号会明显提升。citeturn22view17turn36view0

**异构风控。** 止损放停止量 K 极值外侧，确认 K 若未能带来最基本 follow-through，应在两根 K 内退出。citeturn22view6

**动态出场。**
```text
if stopping_volume_reversal:
    if subsequent_rally hits prior_value_edge and opposite_bar.VZ* >= 2.0:
        exit_all()
    elif no_followthrough within 2 bars:
        exit_all()
```

**第 10 名｜二次推进衰竭与反向高潮量**

**资金逻辑。** 第一推是真冲击，第二推若成交依旧巨大、但净推进长度明显变短，就暴露出趋势的**边际效率衰减**。这类模式本质上是“Upthrust/Distribution 或 Spring/Accumulation”的多腿展开版：第二或第三次冲击把剩余追单和止损都卷进来，随后反向高潮量完成清算。它比失败突破更成熟，但也更晚，因此只排第十。citeturn36view0turn22view23turn22view17

**算法定义。**
```text
Leg1 and Leg2:
  extension_leg2 <= 0.30 * ATR20 beyond leg1_extreme
  sum(Vol_leg2) >= 0.9 * sum(Vol_leg1)
  net_price_progress_leg2 < net_progress_leg1

Reversal Trigger:
  reversal bar closes back into leg1 price zone
  VZ* >= 1.8
  wick ratio >= 0.45
```

**跨资产统计。** 研究合成估计：BTC `55%–59%`，ETH `54%–58%`，XAUUSD `53%–56%`，NQ `56%–60%`。最强上下文是整数位、周高周低、宽幅消息日第二波推进、以及明显的 measured move 完成区。它在 BTC/ETH 和 NQ 上通常都能找到高质量样本，因为这两类市场更容易出现趋势追单堆积。citeturn22view23turn22view17turn22view12turn22view13

**异构风控。** 止损放最终冲击极值外 `0.10–0.15 ATR`。若反向触发后价格又重新夺回最终冲击外侧，说明衰竭判断错误，必须无条件退出。citeturn22view6

**动态出场。**
```text
if exhaustion_reversal:
    if first_pullback_after_reversal on RVOL* <= 0.7 succeeds:
        hold_runner()
    if opposite_climax.VZ* >= 2.3 and reclaim_final_extreme:
        exit_all()
```

## 执行与风控规范

真正把这些扳机做成自动化系统时，成败往往不在形态本身，而在**输入数据和会话标准化**。BTC 与 ETH 应优先使用高质量交易所的报价币成交量、逐笔成交和 taker buy/sell 数据，并尽量把现货与主导永续合约分开计算；不要把低质量 venue 直接并入 RVOL 样本，因为洗售交易会直接污染异常量阈值。citeturn21view0turn21view1turn22view15

XAUUSD 必须坚持两条铁律。第一，**一个模型只绑定一个 broker feed**，不跨 feed 混用 tick volume；第二，所有量阈值都用 `RVOL*` 或 `VZ*` 这种经纪商内条件标准化的异常指标，不用绝对量。这不是保守，而是因为平台官方已经明确，FX/CFD 的 volume 就是价格变动 tick 数，而非真实成交手数；学术研究也证明 tick 与真实量虽相关，但稳定性不足以支撑跨 feed 的绝对比较。citeturn35view5turn35view6turn35view7turn22view8turn22view9

NQ 的特殊优势在于可以把**真实成交量 + 订单簿深度**融合进同一框架，因此它最适合做第 3 名和第 5 名这种依赖吸收与努力—结果背离的扳机。但别因此误以为 NQ 可以无脑放宽阈值；开盘和宏观公告时，量本来就会抬升，所以 NQ 同样需要 minute-of-day 基准与 event-state 分层。Sancetta 对交易到达率的日内轮廓建模、以及微观结构对公告尖峰的刻画，都支持这种设计。citeturn35view8turn21view8turn25view0

组合层面，我更推荐把这十类扳机分成三组而不是混在一起：**反转组**包括第 1、2、5、7、9、10；**吸收组**包括第 3；**中继组**包括第 4、6、8。反转组的共同缺点是会在趋势日里吃到连续止损，因此它们必须加“位置密度”过滤；中继组的共同缺点是会在成熟趋势末端买到终点，因此必须加“趋势年龄/已推进 ATR 数”过滤。简单说，前者不要离开关键位做，后者不要在第三段末端追。这个组合思想与文献中“技术规则优势高度依赖市场状态与样本窗口”的结论一致。citeturn34search1turn34search4turn34search6

## 开放问题与局限

本报告最大的局限，是**不存在一份公开、统一、干净、可比的联合数据集**，同时覆盖 BTC、ETH、XAUUSD 零售 tick volume feed 和 NQ 真量撮合数据，并允许在相同手续费、相同滑点、相同 minute-of-day 框架下，把全部扳机做一键标准回测。因此，文中的各资产胜率区间是**研究合成估计**，不是“某篇论文回测原值”。这一点必须明确。citeturn34search0turn34search4turn34search6

第二，XAUUSD 的可移植性天生弱于 NQ 和经过清洗的 BTC/ETH。原因不是黄金不流动——全球黄金实际上非常深，LBMA 与 WGC 都证明了这一点——而是零售流里你看到的往往只是经纪商 feed 的 tick 活跃度。策略若在一个 feed 上成立，换 feed 后参数几乎总要重标。citeturn35view2turn35view3turn35view4turn35view5turn35view7

第三，BTC/ETH 的量价系统若不先做 venue 质量控制，研究结果会被洗售体量和市场碎片化扭曲。也就是说，加密不是不能做 VPA，而是**先做数据治理，再做信号治理**。citeturn22view15turn22view12turn22view13turn33view0

最终结论只有一句话：**跨 BTC、ETH、XAUUSD、NQ 真正具有统计优势的，不是某根“长得像”的 K 线，而是那些能够把“流动性位置、异常活跃度、订单流失衡、吸收/测试/派发语义”同时量化的结构化扳机。** 在这个标准下，最值得系统化执行的顺序，就是本报告的 Top 10。citeturn24view0turn22view5turn36view0turn35view8turn22view15