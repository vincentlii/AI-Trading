# LR Sweep/Reclaim Mechanism Review

## 结论

1H same-bar reclaim 在语义上最接近“突破失败并在同根确认”，但现有 path-order 并没有显示它比 2/3-bar reclaim 更干净。1H delayed reclaim 的路径数据更好，但它已是另一种机制：更深的 sweep、更慢的修复和更晚的确认，不得与 same-bar 合并。

## 周期对比

| Event | Events | Unique | Sweep depth / ATR | Reclaim inside / ATR | 240m median R | 1200m invalidation-first |
|---|---:|---:|---:|---:|---:|---:|
| 15m micro | 10,873 | 8,530 | 0.738 | 0.425 | 0.195 | 49.66% |
| 1H sweep/reclaim | 8,834 | 6,733 | 0.417 | 0.399 | 0.115 | 48.94% |
| 4H wick-reclaim | 6,787 | 4,884 | 0.215 | 0.326 | 0.008 | 50.41% |

### 15m micro

15m 不是完全无效：240m median R 最高，但 MFE/MAE 中位数分别为 2.646R/2.670R，几乎对称。这更像宽事件池中的高波动触发：既有方向性，也有强烈双向路径噪声。问题不只是周期低，而是“15m 同时承担 event definition 和 execution”使信号过宽。

### 1H sweep/reclaim

1H 把多根 15m 路径压缩成更清晰的 auction failure 单元，事件语义优于 15m。但所有 span 的 invalidation-first 仍在 44%-50%，说明“close 回到 level 内侧”本身仍不足以定义可交易的失败突破。

### 4H wick-reclaim

4H 具有最直观的 wick-rejection 形态，但 4H close 确认后 240m median R 仅 0.008，no-decision 率 13.30%。它更像“形态清晰但确认太晚”：一部分有利推动已被 4H bar 自身吸收。不适合直接进入 execution research。

## 1H Reclaim Span 拆分

| Span | 语义 | Events | Unique | Sweep depth / ATR | Reclaim inside / ATR | 240m median R | Follow 240m | Invalidation-first | No decision |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | same-bar | 6,625 | 5,044 | 0.307 | 0.430 | 0.142 | 65.76% | 50.02% | 3.95% |
| 2 | 1 bar delayed | 1,574 | 1,188 | 0.795 | 0.319 | 0.051 | 72.55% | 46.08% | 8.32% |
| 3 | 2 bars delayed | 635 | 501 | 1.067 | 0.292 | 0.077 | 75.00% | 43.99% | 12.28% |

- **Same-bar**：sweep 浅、close 收回更深，是最符合 failure auction 的形态定义；但 1R 之前 invalidation 仍约 50%，不能只凭形态直接入场。
- **2-bar**：sweep 更深，确认晚 60 分钟；更好的 path-order 可能反映市场已完成修复，也可能是生存者筛选。
- **3-bar**：sweep 中位深度超过 1 ATR，确认晚 120 分钟；它不再是快速失败突破，而是延迟反转。样本也最小，不得因表面 follow-through 高就当 winner。

## 下一版语义要求

1. 保留 1H same-bar 作为“快速失败突破”的核心机制候选。
2. 2/3-bar 必须命名为 delayed reclaim，独立归因，不并入 same-bar。
3. sweep 不能只要穿越 level；下一步需要预注册最低结构语义：first touch、明确的已知 level、无跨过期使用。
4. reclaim 不能只看 close 越回 level；需要在后续 15m 层验证“不立即重回 sweep 区”和“先有利推动”。
