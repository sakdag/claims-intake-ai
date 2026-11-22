from claims_intake.pipeline.conflicts import (
    detect_amount_conflicts,
    extract_amounts,
    parse_eur_amount,
)


def test_parse_european_and_us_amounts() -> None:
    assert parse_eur_amount("19.931,95") == 19931.95
    assert parse_eur_amount("19,931.95") == 19931.95
    assert parse_eur_amount("16400") == 16400.0


def test_extract_amounts_from_text() -> None:
    text = "Form estimate total €16,400. Invoice total 19.931,95 EUR."
    vals = extract_amounts(text)
    assert 16400.0 in vals
    assert 19931.95 in vals


def test_detect_amount_conflicts() -> None:
    docs = [
        {
            "document_id": "1",
            "document_type": "online_form_submission",
            "content": "Estimated total €16,400",
        },
        {
            "document_id": "2",
            "document_type": "invoice",
            "content": "Grand total €19,931.95 including VAT",
        },
    ]
    flags = detect_amount_conflicts(docs)
    assert len(flags) == 1
    assert flags[0].kind == "amount_mismatch"
