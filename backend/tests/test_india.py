from __future__ import annotations

from app.services.evidence_extractor import EvidenceExtractor


def test_extracts_indian_phone_formats() -> None:
    extracted = EvidenceExtractor.extract("Call +91 98765 43210 or 9876543210.")
    assert "+91 98765 43210" in extracted["phone_numbers"]
    assert "9876543210" in extracted["phone_numbers"]


def test_extracts_rupee_amounts_with_indian_grouping() -> None:
    extracted = EvidenceExtractor.extract("The fee is \u20b91,25,000 only.")
    assert extracted["money_amounts"] == ["\u20b91,25,000"]


def test_bank_details_update_is_a_credential_request() -> None:
    extracted = EvidenceExtractor.extract("Update your bank details to receive the refund.")
    assert "credential_request" in extracted["risk_indicators"]


def test_upi_collect_request_is_treated_as_a_payment_authorisation() -> None:
    extracted = EvidenceExtractor.extract(
        "Accept the UPI collect request from 9876543210 to receive \u20b915,000. "
        "Enter your UPI PIN to confirm."
    )
    assert "credential_request" in extracted["risk_indicators"]
    assert "advance_payment" in extracted["risk_indicators"]


def test_aadhaar_safety_advice_is_not_a_credential_request() -> None:
    extracted = EvidenceExtractor.extract(
        "Never share your Aadhaar number, OTP or PIN with anyone."
    )
    assert extracted["requests"] == []
    assert "credential_request" not in extracted["risk_indicators"]
