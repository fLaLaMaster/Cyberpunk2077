from __future__ import annotations

import unittest

from cp77compat.finding_state import (
    Acknowledgement,
    classify_findings,
    finding_fingerprint,
)
from cp77compat.models import Finding


def finding(summary: str = "1 overlapping target", severity: str = "warning") -> Finding:
    return Finding(
        rule_id="TEST-OVERLAP",
        severity=severity,
        confidence="high",
        summary=summary,
        explanation="Example",
        participants=["Second Mod", "First Mod"],
        evidence=[{"identity": r"base\example.target", "count": 1}],
    )


class FindingStateTests(unittest.TestCase):
    def test_fingerprint_ignores_counts_and_participant_order(self) -> None:
        first = finding("1 overlapping targets")
        second = finding("24 overlapping targets")
        second.participants.reverse()
        self.assertEqual(finding_fingerprint(first), finding_fingerprint(second))

    def test_classifies_acknowledged_changed_and_stale_entries(self) -> None:
        previous = finding().to_dict()
        current = finding(severity="error")
        fingerprint = finding_fingerprint(current)
        stale_fingerprint = "f" * 64
        state, diff, stale = classify_findings(
            [current],
            [
                Acknowledgement(fingerprint, "Expected overlap"),
                Acknowledgement(stale_fingerprint, "Old finding"),
            ],
            [previous],
        )
        self.assertEqual("acknowledged", current.status)
        self.assertEqual("changed", current.change)
        self.assertEqual("Expected overlap", current.acknowledgement)
        self.assertEqual(1, state["acknowledged"])
        self.assertEqual(1, state["stale_acknowledgements"])
        self.assertEqual(1, diff["summary"]["changed"])
        self.assertEqual(stale_fingerprint, stale[0]["fingerprint"])

    def test_reports_new_and_resolved_findings(self) -> None:
        previous = finding("Old identity")
        current = finding("New identity")
        _, diff, _ = classify_findings([current], [], [previous.to_dict()])
        self.assertEqual(1, diff["summary"]["new"])
        self.assertEqual(1, diff["summary"]["resolved"])

    def test_evidence_order_does_not_create_a_changed_finding(self) -> None:
        previous = finding()
        previous.evidence = [
            {"identity": "shared", "references": [{"identity": "b"}, {"identity": "a"}]}
        ]
        current = finding()
        current.evidence = [
            {"identity": "shared", "references": [{"identity": "a"}, {"identity": "b"}]}
        ]
        _, diff, _ = classify_findings([current], [], [previous.to_dict()])
        self.assertEqual(0, diff["summary"]["changed"])
        self.assertEqual(1, diff["summary"]["unchanged"])


if __name__ == "__main__":
    unittest.main()
