from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from research_pipeline.cli.research import main
from research_pipeline.runners.root_cause_investigation import run_root_cause_investigation


class RootCauseInvestigationTests(unittest.TestCase):
    def test_runner_writes_root_cause_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "cache"
            output = Path(tmp) / "out"
            self._write_fixture_artifacts(root)

            result = run_root_cause_investigation(
                strategy="liquidity_reversal",
                artifact_root=root,
                output_dir=output,
            )

            self.assertEqual(result.primary_decision, "D")
            self.assertEqual(result.next_pr_recommendation, "PR 11G-QA-fix-3")
            self.assertTrue((output / "root_cause_report.md").exists())
            self.assertTrue((output / "root_cause_result.json").exists())
            self.assertTrue((output / "lineage_field_presence_matrix.csv").exists())
            self.assertTrue((output / "artifact_stage_flow.md").exists())
            self.assertTrue((output / "risky_writer_functions.jsonl").exists())
            self.assertTrue((output / "proposed_fix_plan.md").exists())

            with (output / "lineage_field_presence_matrix.csv").open(encoding="utf-8") as handle:
                matrix = list(csv.DictReader(handle))
            trade_rows = [row for row in matrix if row["field"] == "trade_id"]
            self.assertTrue(trade_rows)
            self.assertTrue(any(row["present_count"] == "0" for row in trade_rows))

    def test_cli_runs_root_cause_investigation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "cache"
            output = Path(tmp) / "out"
            self._write_fixture_artifacts(root)

            exit_code = main(
                [
                    "root-cause-investigation",
                    "--strategy",
                    "liquidity_reversal",
                    "--artifact-root",
                    str(root),
                    "--output-dir",
                    str(output),
                ]
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads((output / "root_cause_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["primary_decision"], "D")

    @staticmethod
    def _write_fixture_artifacts(root: Path) -> None:
        filter_dir = root / "minimal_lr_v0_filter_stage6e" / "10000w"
        filter_dir.mkdir(parents=True)
        (filter_dir / "minimal_lr_v0_filter_results.jsonl").write_text(
            json.dumps(
                {
                    "candidate_id": "c1",
                    "event_id": "e1",
                    "sweep_time": 100,
                    "reclaim_time": 200,
                    "signal_time": 300,
                    "entry_time": 400,
                    "structure_time": 50,
                    "formal_approved": True,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (filter_dir / "minimal_lr_v0_execution_results.jsonl").write_text(
            json.dumps(
                {
                    "candidate_id": "c1",
                    "closed_trade": True,
                    "exit_reason": "time_cut_exit",
                    "net_R": 0.2,
                    "mfe_R": 0.8,
                    "mae_R": 0.1,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        sizing_dir = root / "stage6e_sizing" / "10000w"
        sizing_dir.mkdir(parents=True)
        with (sizing_dir / "stage6c_sizing_candidates.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["candidate_id", "event_id", "proposal_approved", "entry_time"])
            writer.writeheader()
            writer.writerow({"candidate_id": "c1", "event_id": "e1", "proposal_approved": "True", "entry_time": "400"})


if __name__ == "__main__":
    unittest.main()
