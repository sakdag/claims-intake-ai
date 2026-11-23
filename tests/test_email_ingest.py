from claims_intake.pipeline.email_ingest import email_to_polycontext, wrap_poly_for_inbox


def _sample_mime(*, claim_header: str | None = "260009999") -> bytes:
    headers = [
        "From: claimant@example.com",
        "To: claims@elmstone.example",
        "Subject: FNOL for claim 260009999 snow damage",
        "MIME-Version: 1.0",
        'Content-Type: multipart/mixed; boundary="bound"',
        "",
        "--bound",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "Hello, our porch roof collapsed under snow on 2025-12-02.",
        "Policy PZ-PHI-000000099.",
        "--bound",
        "Content-Type: text/plain; charset=utf-8",
        "Content-Disposition: attachment; filename=invoice.txt",
        "",
        "INVOICE total EUR 1200.00",
        "--bound--",
        "",
    ]
    if claim_header:
        headers.insert(3, f"X-Claim-Id: {claim_header}")
    return "\r\n".join(headers).encode("utf-8")


def test_email_to_polycontext_extracts_docs_and_claim_id() -> None:
    poly = email_to_polycontext(_sample_mime())
    assert poly["claim"]["claimId"] == "260009999"
    assert poly["intakeChannel"] == "email"
    assert len(poly["contextDocuments"]) >= 2
    assert any("snow" in d["extractedDocumentContent"].lower() for d in poly["contextDocuments"])


def test_wrap_poly_for_inbox() -> None:
    poly = email_to_polycontext(_sample_mime())
    package = wrap_poly_for_inbox(poly)
    assert package["data"]["claim"]["claimId"] == "260009999"
    assert "note" in package
