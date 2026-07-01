"""CLI summary formatting tests."""

from __future__ import annotations

from coffeebench_ocl.phase1 import report_brief


def test_report_brief_keeps_cli_output_compact() -> None:
    brief = report_brief(
        {
            "arm": "B3",
            "label": "OCL-Warning",
            "report_path": "outputs/run_report.json",
            "trajectory_path": "outputs/run.json",
            "ocl": {
                "events_path": "outputs/run.ocl.jsonl",
                "summary_path": "outputs/run.ocl.summary.json",
                "summary": {
                    "validation_counts": {"pass": 1},
                    "blocked_action_count": 0,
                },
            },
            "result": {
                "main_agent": "roaster_A",
                "actual_final_day": 0,
                "terminated_early": None,
                "marketplace_summary": {"total_deals": 0},
                "agents": {
                    "roaster_A": {
                        "net_income": -30.0,
                        "usage": {"model": "qwen/qwen-plus", "n_calls": 1, "cost": 0.0},
                        "audit": {
                            "balance_sheet": {
                                "true_cash": 14970.0,
                                "true_equity": 15146.4,
                            }
                        },
                    }
                },
            },
        }
    )

    assert brief["arm"] == "B3"
    assert brief["main_agent_result"]["model"] == "qwen/qwen-plus"
    assert brief["ocl_summary"]["validation_counts"] == {"pass": 1}
    assert "result" not in brief
