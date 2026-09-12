from __future__ import annotations

from metrics import AgentMetrics, summarize_metrics


def test_summarize_metrics() -> None:
    summary = summarize_metrics(
        [
            AgentMetrics(True, 2, 1, 0, 2, "finished"),
            AgentMetrics(False, 3, 1, 2, 1, "parse_error"),
        ]
    )

    assert summary["cases"] == 2
    assert summary["completion_rate"] == 0.5
    assert summary["average_llm_calls"] == 2.5
    assert summary["termination_counts"] == {
        "finished": 1,
        "parse_error": 1,
    }


def test_empty_metrics_have_zero_values() -> None:
    summary = summarize_metrics([])

    assert summary["cases"] == 0
    assert summary["completion_rate"] == 0.0
    assert summary["termination_counts"] == {}
