# LR Multi-Timeframe VPA Causal Event Research 实施计划

## 实施状态

代码与 TDD 已于 2026-06-19 完成。73 项 LR 相关回归测试、compileall 与 `git diff --check` 通过；2021-01-01 至 2021-01-14 两次独立 smoke 均生成 232 个 event-level、171 个 unique physical events，audit 为 pass、0 violation，五类核心 artifact hash 完全一致。完整 development 长任务尚未执行，按约定交由用户手动运行。

实现中经测试审查修正一项先验：15m control 保留旧 4H ATR sweep-depth cap；1H 与 4H 不使用 event ATR depth 硬过滤，避免在 timeframe comparison 前预先删除深 sweep。Diagnostic R 仍严格使用各事件周期 ATR。

> 执行方式：在 `research/lr-exits` 当前工作区内按 TDD 逐项实施。项目规则禁止未获授权的 commit，因此本计划不包含 commit 步骤。

**目标：** 建立 15m control、1H sweep/reclaim、4H wick-reclaim 三类因果事件池，输出 VPA attribution、diagnostic anatomy、因果审计与集中研究报告。

**架构：** 策略层拆成 event scanner、VPA attribution、event anatomy 三个无 I/O 模块；Research Pipeline runner 负责读取 BTC/ETH confirmed candles、调用模块、确定性写入 artifact、执行 audit 和生成报告；现有 `lr-causal-rebuild` CLI 新增 `multitimeframe-events` stage。

**技术栈：** Python dataclass、标准库 bisect/statistics/hashlib/json、现有 CandleRepository、Research Pipeline artifact contract、unittest。

---

## 文件结构

- 新增 `trading_system/strategies/trend_price_volume_v1/lr_multitimeframe_event.py`：时间周期 policy、event dataclass、generic causal scanner。
- 新增 `trading_system/strategies/trend_price_volume_v1/lr_vpa_attribution.py`：只读 causal VPA features 与 post-signal volume labels。
- 新增 `trading_system/strategies/trend_price_volume_v1/lr_event_anatomy.py`：diagnostic R、future path、MFE/MAE、time-to-R。
- 新增 `research_pipeline/runners/lr_multitimeframe_event_research.py`：数据装载、level validity、汇总、审计、artifact 和集中报告。
- 修改 `research_pipeline/cli/research.py`：新增 stage dispatch，不改变现有 anatomy/entry-tournament。
- 新增 `tests/test_lr_multitimeframe_event.py`。
- 新增 `tests/test_lr_vpa_attribution.py`。
- 新增 `tests/test_lr_event_anatomy.py`。
- 新增 `research_pipeline/tests/test_lr_multitimeframe_event_research.py`。
- 更新 `AI Trading/08_复盘与报告/`：只在 smoke 通过后记录实现状态和全量手动命令。

## Task 1：多周期 causal event scanner

- [ ] 新增失败测试：15m control 与旧语义一致，最多四根 reclaim。
- [ ] 新增失败测试：1H 同根、两根、三根 reclaim 分别输出 `reclaim_span_bars=1/2/3`，第四根不得成立。
- [ ] 新增失败测试：4H 只接受同根 wick-reclaim，不接受跨 bar reclaim。
- [x] 新增失败测试：未确认 bar 与 level confirmed_time 之前的 bar 不得生成 event；15m control 保留 4H ATR depth cap，1H/4H 不设 depth 硬门槛。
- [ ] 新增失败测试：`signal_time == reclaim_bar_open + timeframe_ms`，每个 level 只保留首个事件。
- [ ] 新增失败测试：`physical_event_key` 不含 level identity；同物理事件跨 family key 相同。
- [ ] 运行 RED：

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_lr_multitimeframe_event -v
```

预期：模块不存在或 API 不存在而失败。

- [ ] 实现最小 API：

```python
EVENT_POLICIES = {
    "15m_micro": EventPolicy("15m_micro", 15 * 60_000, 4, False),
    "1H_sweep_reclaim": EventPolicy("1H_sweep_reclaim", 60 * 60_000, 3, False),
    "4H_wick_reclaim": EventPolicy("4H_wick_reclaim", 4 * 60 * 60_000, 1, True),
}

def detect_multitimeframe_events(*, levels, candles, atr_at, policy, instrument): ...
```

- [ ] 保留 `level_id/family`，并记录 `sweep_start_bar_time`、`sweep_extreme_bar_time`、`reclaim_bar_time`、`signal_close`、`event_atr`、`reclaim_span_bars`、`feature_cutoff_time`。
- [ ] 运行 GREEN，并同时运行旧 scanner 回归测试。

## Task 2：Causal VPA attribution

- [ ] 新增失败测试：relative volume 与 range expansion 的 baseline 只包含当前 bar 之前 20 根 confirmed candles。
- [ ] 新增失败测试：volume percentile 只使用此前最多 100 根 confirmed candles；少于 20 根时值为 null 并输出 sample count。
- [ ] 新增失败测试：1H 多 bar event 的 sweep feature取 sweep extreme candle；combined volume覆盖完整 event window。
- [ ] 新增失败测试：directional wick ratio 与 direction-aware CLV 对 long/short 正确。
- [ ] 新增失败测试：所有 feature row 均为 `row_role=tradable_feature`，`max_source_time <= feature_cutoff_time == signal_time`。
- [ ] 新增失败测试：follow-through volume 与 post-reclaim contraction/expansion 只写入 `row_role=diagnostic_label`，source time 严格晚于 signal_time。
- [ ] 运行 RED：

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_lr_vpa_attribution -v
```

- [ ] 实现 `build_vpa_feature_row(...)` 与 `build_post_signal_volume_label(...)`，不调用任何门控、不输出 pass/fail score。
- [ ] 使用预定义 causal percentile buckets：`q1=[0,0.25)`、`q2=[0.25,0.5)`、`q3=[0.5,0.75)`、`q4=[0.75,1]`。
- [ ] 运行 GREEN。

## Task 3：Diagnostic event anatomy

- [ ] 新增失败测试：signal close 与 ATR 都来自 signal_time 前已确认 event timeframe candles。
- [ ] 新增失败测试：long/short invalidation 与 1R 严格使用 `0.10 * event ATR` buffer。
- [ ] 新增失败测试：七个 horizon 的 signed R 与 ATR-normalized return 使用 signal 后 15m confirmed close。
- [ ] 新增失败测试：1200 分钟 MFE/MAE、0.5R/1R/1.5R/2R 首次到达时间正确。
- [ ] 新增失败测试：同一 15m bar 同时触及 invalidation 和目标时，目标 time-to-R 不成立且 invalidation 优先。
- [ ] 新增失败测试：240 分钟 follow-through 与 1200 分钟 invalidation-first 支持 true/false/unresolved。
- [ ] 运行 RED：

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_lr_event_anatomy -v
```

- [ ] 实现 `build_event_anatomy(event, future_15m)`；所有未来字段写入 `row_role=diagnostic_label`，不得返回 tradable feature。
- [ ] 运行 GREEN。

## Task 4：Research Pipeline runner、汇总与集中报告

- [ ] 新增失败测试：runner 仅接受 development，拒绝 `end >= 2024-12-01`。
- [ ] 新增失败测试：只读取 BTC/ETH 的 15m、1H、4H confirmed candles，查询结束时间不超过 development end。
- [ ] 新增失败测试：三类 timeframe 同时输出，正式 `closed_trade_rows.jsonl` 与 execution artifacts 为空。
- [ ] 新增失败测试：event-level count 与 unique physical event count 分开；汇总包含 asset/direction/year/session/level family/timeframe/VPA bucket。
- [ ] 新增失败测试：报告包含五个指定章节且不含硬 winner。
- [ ] 新增失败测试：CLI dispatch 到 `multitimeframe-events`，不调用 entry tournament。
- [ ] 运行 RED：

```powershell
.\.venv\Scripts\python.exe -B -m unittest research_pipeline.tests.test_lr_multitimeframe_event_research -v
```

- [ ] 实现 runner，按稳定 key 排序并用 `json.dumps(..., sort_keys=True)` 写 JSONL。
- [ ] 输出 `event_rows`、`vpa_feature_rows`、`diagnostic_label_rows`、`anatomy_rows`、`summary_rows`、`causality_audit`、manifest、artifact index 与 consolidated report。
- [ ] 报告 recommendation 仅输出证据方向与限制，禁止 `selected_variant`、`winner` 或正式化状态。
- [ ] 运行 GREEN。

## Task 5：Causality audit 与 artifact determinism

- [ ] 新增失败测试：以下任一情况必须使 audit fail：未确认 event bar、signal_time 不等于 reclaim close、feature source 晚于 signal、future label 混入 feature、holdout_accessed 非 false。
- [ ] 新增失败测试：同一组核心 rows 序列化两次的 SHA-256 完全一致。
- [ ] 新增失败测试：重复物理事件不被静默删除，event 与 unique physical count 可复算。
- [ ] 实现 `audit_multitimeframe_research(...)` 与 deterministic core hash map。
- [ ] 运行 scanner/VPA/anatomy/runner 全部测试。

## Task 6：两周 smoke 与完成验证

- [ ] 运行编译和聚焦测试：

```powershell
.\.venv\Scripts\python.exe -B -m compileall trading_system research_pipeline tests
.\.venv\Scripts\python.exe -B -m unittest tests.test_lr_multitimeframe_event tests.test_lr_vpa_attribution tests.test_lr_event_anatomy research_pipeline.tests.test_lr_multitimeframe_event_research tests.test_lr_causal_entry research_pipeline.tests.test_lr_causal_rebuild research_pipeline.tests.test_lr_entry_tournament -v
git diff --check
```

- [ ] 运行 2021-01-01 至 2021-01-15 development smoke 两次，使用不同 output root。
- [ ] 比较两次核心 artifact SHA-256；任何差异都阻断全量运行。
- [ ] 核验 audit：时间违规 0、feature/label contamination 0、holdout access 0、核心 hash mismatch 0。
- [ ] 更新 Obsidian 当前状态，明确 Restricted Variant B suspended、Entry Tournament v2 failed diagnostic、无 winner。
- [ ] 停止自动执行，在完整 development 长任务前向用户提供手动命令。

## 验收标准

- 三个 timeframe scanner 均有独立因果测试并通过。
- VPA tradable features 与 post-signal labels 物理隔离。
- Diagnostic R 与七个 horizon 可由逐事件 rows 复算。
- Audit 能主动拒绝 lookahead、holdout、未确认 bar 和 artifact nondeterminism。
- Smoke 两次核心 hashes 相同。
- 不产生 closed trade，不调用旧五种 entry，不修改正式配置或 RiskEngine。
