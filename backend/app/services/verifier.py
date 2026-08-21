import re
import logging
from typing import Dict, Any, List, Set

logger = logging.getLogger(__name__)

class VerificationEngine:
    """
    Programmatic Number Verifier (Non-LLM).
    Extracts all numerical values from Gemini-generated briefs and asserts
    that every value exists in the closed Evidence Bundle.
    """
    
    # Common helper numbers and dates that are ignored from hallucination checking
    ALLOWED_CONSTANTS: Set[float] = {
        0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 100.0,
        2024.0, 2025.0, 2026.0, 2027.0
    }

    @classmethod
    def _extract_numbers_from_text(cls, text: str) -> List[float]:
        """
        Regex to find all numeric expressions: currency, percentage, counts, decimals.
        e.g., $1.2M, 50,000, 15%, 2.5
        """
        numbers = []
        # Find raw integers/floats (e.g. 50000, 2.5, 15)
        # Matches numbers optionally with commas
        raw_matches = re.findall(r'\b\d+(?:,\d+)*(?:\.\d+)?\b', text)
        for m in raw_matches:
            try:
                # Remove commas
                val = float(m.replace(",", ""))
                numbers.append(val)
            except ValueError:
                continue
        return numbers

    @classmethod
    def _extract_all_bundle_values(cls, data: Any) -> Set[float]:
        """
        Recursively extract all numeric values from the Evidence Bundle.
        """
        values = set()
        if isinstance(data, dict):
            for k, v in data.items():
                values.update(cls._extract_all_bundle_values(v))
        elif isinstance(data, list):
            for item in data:
                values.update(cls._extract_all_bundle_values(item))
        elif isinstance(data, (int, float)):
            values.add(float(data))
        elif isinstance(data, str):
            # Check if string represents a number
            cleaned = data.replace(",", "").replace("$", "").replace("Rs.", "").replace("Rs", "").strip()
            # Handle abbreviations like 'M' or 'k'
            multiplier = 1.0
            if cleaned.lower().endswith('m'):
                multiplier = 1000000.0
                cleaned = cleaned[:-1]
            elif cleaned.lower().endswith('k'):
                multiplier = 1000.0
                cleaned = cleaned[:-1]
            try:
                values.add(float(cleaned) * multiplier)
            except ValueError:
                pass
        return values

    @classmethod
    def verify_brief(cls, brief_text: str, evidence_bundle: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare extracted text numbers against evidence values.
        """
        extracted = cls._extract_numbers_from_text(brief_text)
        bundle_values = cls._extract_all_bundle_values(evidence_bundle)
        
        unverified_numbers = []
        for num in extracted:
            # Check if number is in allowed constants
            if num in cls.ALLOWED_CONSTANTS:
                continue
            
            # Check for exact or close float matching (e.g. percentage 15 vs 0.15)
            matched = False
            for b_val in bundle_values:
                if abs(num - b_val) < 1e-4:
                    matched = True
                    break
                # Handle percentage scale differences (e.g. 75 vs 0.75)
                if abs(num / 100.0 - b_val) < 1e-4 or abs(num * 100.0 - b_val) < 1e-4:
                    matched = True
                    break
            
            if not matched:
                unverified_numbers.append(num)

        is_valid = len(unverified_numbers) == 0

        return {
            "verified": is_valid,
            "unverified_count": len(unverified_numbers),
            "unverified_numbers": list(set(unverified_numbers)),
            "extracted_numbers": list(set(extracted)),
            "bundle_values": list(bundle_values)
        }

verification_engine = VerificationEngine()
