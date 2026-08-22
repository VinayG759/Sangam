"""
Unit tests for VerificationEngine.

Tests cover:
- Number extraction from text (integers, floats, comma-separated)
- Bundle value extraction (nested dicts, lists, strings with currency)
- Verification logic (exact match, percentage scale, lakh scale)
- Edge cases (empty inputs, booleans, allowed constants)
"""

import pytest
from app.services.verifier import VerificationEngine, verification_engine


class TestExtractNumbersFromText:
    """Tests for _extract_numbers_from_text."""

    def test_basic_integers(self):
        nums = VerificationEngine._extract_numbers_from_text("There are 50 reports and 120 issues")
        assert 50.0 in nums
        assert 120.0 in nums

    def test_floats(self):
        nums = VerificationEngine._extract_numbers_from_text("Score is 85.72 and urgency is 4.5")
        assert 85.72 in nums
        assert 4.5 in nums

    def test_comma_separated_numbers(self):
        nums = VerificationEngine._extract_numbers_from_text("Budget of 45,00,000 allocated for 2,500 residents")
        assert 4500000.0 in nums
        assert 2500.0 in nums

    def test_empty_text(self):
        nums = VerificationEngine._extract_numbers_from_text("")
        assert nums == []

    def test_no_numbers(self):
        nums = VerificationEngine._extract_numbers_from_text("No numbers here at all")
        assert nums == []

    def test_percentages_extracted_as_raw(self):
        nums = VerificationEngine._extract_numbers_from_text("Coverage at 75% and growth at 3.5%")
        assert 75.0 in nums
        assert 3.5 in nums


class TestExtractBundleValues:
    """Tests for _extract_all_bundle_values."""

    def test_flat_dict(self):
        vals = VerificationEngine._extract_all_bundle_values({"a": 10, "b": 20.5})
        assert 10.0 in vals
        assert 20.5 in vals

    def test_nested_dict(self):
        vals = VerificationEngine._extract_all_bundle_values({
            "outer": {"inner": 42.0},
            "list_field": [1, 2, 3]
        })
        assert 42.0 in vals
        assert 1.0 in vals
        assert 3.0 in vals

    def test_string_numbers(self):
        vals = VerificationEngine._extract_all_bundle_values({"val": "4500000"})
        assert 4500000.0 in vals

    def test_currency_prefix_stripped(self):
        vals = VerificationEngine._extract_all_bundle_values({"val": "Rs.2500000"})
        assert 2500000.0 in vals

    def test_indian_rupee_symbol(self):
        vals = VerificationEngine._extract_all_bundle_values({"val": "₹2500000"})
        assert 2500000.0 in vals

    def test_magnitude_suffix_m(self):
        vals = VerificationEngine._extract_all_bundle_values({"val": "1.5M"})
        assert 1500000.0 in vals

    def test_magnitude_suffix_k(self):
        vals = VerificationEngine._extract_all_bundle_values({"val": "50K"})
        assert 50000.0 in vals

    def test_magnitude_suffix_crore(self):
        vals = VerificationEngine._extract_all_bundle_values({"val": "2Cr"})
        assert 20000000.0 in vals

    def test_magnitude_suffix_lakh(self):
        vals = VerificationEngine._extract_all_bundle_values({"val": "45Lakh"})
        assert 4500000.0 in vals

    def test_boolean_skipped(self):
        vals = VerificationEngine._extract_all_bundle_values({"flag": True, "count": 5})
        assert True not in vals  # True == 1 as int, but should be skipped
        assert 5.0 in vals
        assert 1.0 not in vals  # bool True should NOT be extracted as 1.0

    def test_none_handled(self):
        vals = VerificationEngine._extract_all_bundle_values(None)
        assert vals == set()

    def test_empty_dict(self):
        vals = VerificationEngine._extract_all_bundle_values({})
        assert vals == set()


class TestVerifyBrief:
    """Tests for verify_brief — the main verification method."""

    def test_all_numbers_verified(self, sample_evidence_bundle):
        # Brief text only uses numbers from the bundle
        brief = "There are 5 reports with average urgency of 4.2 and allocated budget of 2500000."
        result = verification_engine.verify_brief(brief, sample_evidence_bundle)
        assert result["verified"] is True
        assert result["unverified_count"] == 0

    def test_hallucinated_number_detected(self, sample_evidence_bundle):
        # 999999 does NOT exist in the bundle
        brief = "There are 5 reports. The government wasted 999999 rupees."
        result = verification_engine.verify_brief(brief, sample_evidence_bundle)
        assert result["verified"] is False
        assert 999999.0 in result["unverified_numbers"]

    def test_allowed_constants_pass(self, sample_evidence_bundle):
        # Years and common numbers should be ignored
        brief = "In 2025 there were 5 reports. 100 percent coverage is needed."
        result = verification_engine.verify_brief(brief, sample_evidence_bundle)
        assert result["verified"] is True

    def test_percentage_scale_matching(self):
        # Brief says 45, bundle has 0.45 → should match via percentage scale
        bundle = {"vulnerability_index": 0.45}
        brief = "Vulnerability at 45 percent."
        result = verification_engine.verify_brief(brief, bundle)
        assert result["verified"] is True

    def test_empty_brief(self, sample_evidence_bundle):
        result = verification_engine.verify_brief("", sample_evidence_bundle)
        assert result["verified"] is True
        assert result["extracted_numbers"] == []

    def test_empty_bundle(self):
        brief = "The cost is 50000."
        result = verification_engine.verify_brief(brief, {})
        assert result["verified"] is False
        assert 50000.0 in result["unverified_numbers"]

    def test_output_structure(self, sample_evidence_bundle):
        brief = "5 reports found."
        result = verification_engine.verify_brief(brief, sample_evidence_bundle)
        assert "verified" in result
        assert "unverified_count" in result
        assert "unverified_numbers" in result
        assert "extracted_numbers" in result
        assert "bundle_values" in result
        assert isinstance(result["verified"], bool)
        assert isinstance(result["unverified_count"], int)
        assert isinstance(result["unverified_numbers"], list)
