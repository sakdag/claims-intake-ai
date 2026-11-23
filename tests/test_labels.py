import json
from pathlib import Path

from claims_intake.data.labels import (
    derive_labels_for_polycontext,
    stratified_claim_split,
)

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "polycontexts_sample.json"


def test_derive_labels_from_fixture() -> None:
    rows = json.loads(FIXTURE.read_text())
    lab = derive_labels_for_polycontext(rows[0])
    assert lab["claim_id"] == "260001894"
    assert len(lab["document_types"]) == 11
    assert "claimId" in lab["extraction_gold"]
    assert lab["policy_checks"]["policy_status"]["status"] in {
        "PASSED",
        "FAILED",
        "UNRESOLVABLE",
    }


def test_split_sizes() -> None:
    labels = [
        {
            "claim_id": f"c{i}",
            "product": "PHI" if i % 2 == 0 else "PBI",
            "loss_event": "Flood" if i % 3 == 0 else "Fire",
        }
        for i in range(400)
    ]
    split = stratified_claim_split(labels, n_dev=50, n_test=150, seed=42)
    assert split["n_dev"] == 50
    assert split["n_test"] == 150
    assert set(split["dev"]).isdisjoint(set(split["test"]))
