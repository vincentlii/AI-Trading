# Legacy Migration Manifest

## 结论

legacy scripts 暂不删除，只保留兼容 wrapper 或历史复现用途。

## 当前主工作流

```powershell
python -m research_pipeline.cli.research full-audit --strategy liquidity_reversal --artifact-dir <artifact_dir> --output-dir <output_dir>
python -m research_pipeline.cli.research lr-robustness-validation --artifact-dir <artifact_dir> --output-dir <output_dir>
python -m research_pipeline.cli.research lr-robustness-fix --artifact-dir <artifact_dir> --output-dir <output_dir>
```

## 未来统一入口目标

```powershell
python -m research_pipeline.cli.research run --strategy liquidity_reversal --config <config> --mode full-research
python -m research_pipeline.cli.research full-audit --strategy liquidity_reversal --artifact-dir <dir>
python -m research_pipeline.cli.research robustness --strategy liquidity_reversal --artifact-dir <dir>
```

## Legacy 边界

- legacy scripts 不得绕过 full-audit。
- legacy output 不得直接作为 robustness input。
- old PR11C-PR11G artifacts 不得覆盖 final clean rebuild evidence。
