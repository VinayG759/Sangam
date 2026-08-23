import re
import logging
from typing import Dict, Any, List, Set

logger = logging.getLogger(__name__)


class VerificationEngine:
    """
    Programmatic Number Verifier (Non-LLM).
    Extracts all numerical values from Gemini-generated briefs and asserts
    that every value exists in the closed Evidence Bundle.

    This prevents hallucinated statistics from reaching policy makers.
    Any number in the brief that cannot be traced back to the evidence
    bundle is flagged as unverified.
    """

    # Numbers exempt from checking.
    #
    # Kept deliberately small. The previous list also exempted 2, 3, 4, 5 and
    # 10, which are exactly the magnitudes a brief uses for counts -- "3
    # districts affected", "5 blocks stalled". Exempting them meant a wrong
    # count could never be caught. 0 and 1 are unavoidable in prose, 100 is
    # needed for "100 percent", and years are not claims about the data.
    ALLOWED_CONSTANTS: Set[float] = {
        0.0, 1.0, 100.0,
        2019.0, 2020.0, 2021.0, 2022.0, 2023.0, 2024.0,
        2025.0, 2026.0, 2027.0, 2028.0,
    }

    # Tolerance for floating point comparison
    FLOAT_TOLERANCE = 1e-4

    # Relative tolerance permitted when a brief rounds a figure (97.3 for
    # 97.31). Declared rather than implicit, because every loosening here is
    # a loosening of the guarantee the whole system rests on.
    ROUNDING_TOLERANCE = 1e-3

    @classmethod
    def _extract_numbers_from_text(cls, text: str) -> List[float]:
        """
        Regex to find all numeric expressions: currency, percentage, counts, decimals.
        e.g., ₹1.2M, 50,000, 15%, 2.5, Rs.45,00,000

        Handles Indian lakh/crore comma formatting (e.g., 45,00,000) and
        Western formatting (e.g., 4,500,000).
        """
        if not text:
            return []

        numbers = []
        # Match numbers with optional commas and decimal points
        raw_matches = re.findall(r'\b\d+(?:,\d+)*(?:\.\d+)?\b', text)
        for m in raw_matches:
            try:
                val = float(m.replace(",", ""))
                numbers.append(val)
            except ValueError:
                continue
        return numbers

    @classmethod
    def _extract_all_bundle_values(cls, data: Any) -> Set[float]:
        """
        Recursively extract all numeric values from the Evidence Bundle.
        Handles nested dicts, lists, raw numbers, and string-encoded numbers
        with currency prefixes and magnitude suffixes (M, K, Cr, L).
        """
        values = set()
        if data is None:
            return values

        if isinstance(data, dict):
            for k, v in data.items():
                values.update(cls._extract_all_bundle_values(v))
        elif isinstance(data, list):
            for item in data:
                values.update(cls._extract_all_bundle_values(item))
        elif isinstance(data, bool):
            # bool is subclass of int in Python, skip it
            pass
        elif isinstance(data, (int, float)):
            values.add(float(data))
        elif isinstance(data, str):
            # Strip currency symbols and whitespace
            cleaned = data.replace(",", "").replace("$", "").replace("₹", "")
            cleaned = cleaned.replace("Rs.", "").replace("Rs", "").strip()

            # Handle magnitude abbreviations
            multiplier = 1.0
            lower = cleaned.lower()
            if lower.endswith('cr') or lower.endswith('crore'):
                multiplier = 10000000.0
                cleaned = re.sub(r'(?i)cr(?:ore)?$', '', cleaned).strip()
            elif lower.endswith('l') or lower.endswith('lakh') or lower.endswith('lakhs'):
                multiplier = 100000.0
                cleaned = re.sub(r'(?i)l(?:akhs?)?$', '', cleaned).strip()
            elif lower.endswith('m'):
                multiplier = 1000000.0
                cleaned = cleaned[:-1].strip()
            elif lower.endswith('k'):
                multiplier = 1000.0
                cleaned = cleaned[:-1].strip()

            try:
                values.add(float(cleaned) * multiplier)
            except ValueError:
                pass
        return values

    @classmethod
    def _numbers_match(cls, num: float, bundle_val: float) -> bool:
        """
        Does `num` legitimately represent `bundle_val`?

        This method is the whole anti-hallucination mechanism, so it is
        deliberately narrow. The previous implementation also accepted
        num*100, num*100_000 and bundle/100_000 as matches. Those blanket
        scale shifts meant each bundle value effectively covered five
        different numbers, and fabricated figures walked straight through:
        against a bundle of {households: 50444, coverage: 97.31} the invented
        values 504.44, 5044400, 9731 and 0.9731 were all reported "verified".

        Exactly three things count as a match now:

        1. Equality, within float tolerance.
        2. Rounding, within ROUNDING_TOLERANCE relative -- a brief may quote
           97.3 for a stored 97.31. Tight enough that a different figure
           cannot slip through, loose enough to allow natural prose.
        3. Ratio expressed as a percentage, and only in that direction, and
           only when the stored value really is a ratio (0..1) and the quoted
           value really is a percentage (0..100). Without both guards this
           single rule is what let 9731 match 97.31.

        Anything else is a fabrication as far as this system is concerned. If
        a brief needs to quote a figure in another form, the evidence bundle
        must carry it in that form -- completing the bundle is the bundle
        builder's job, not the verifier's job to guess.
        """
        # 1. exact
        if abs(num - bundle_val) < cls.FLOAT_TOLERANCE:
            return True

        # 2. rounding, same order of magnitude only
        scale = max(abs(bundle_val), 1.0)
        if abs(num - bundle_val) / scale < cls.ROUNDING_TOLERANCE:
            return True

        # 3. ratio -> percentage, bounded on both sides
        if 0.0 <= bundle_val <= 1.0 and 0.0 <= num <= 100.0:
            if abs(num / 100.0 - bundle_val) < cls.FLOAT_TOLERANCE:
                return True

        return False

    @classmethod
    def verify_brief(cls, brief_text: str, evidence_bundle: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare extracted text numbers against evidence values.

        Args:
            brief_text: The full text of the generated policy brief.
            evidence_bundle: The closed evidence JSON used to generate the brief.

        Returns:
            Dict with verification result:
            - verified (bool): True if all numbers trace to the bundle.
            - unverified_count (int): Number of unverifiable figures.
            - unverified_numbers (list): The specific unverifiable values.
            - extracted_numbers (list): All numbers found in the brief.
            - bundle_values (list): All numbers found in the evidence bundle.
        """
        if not brief_text:
            return {
                "verified": True,
                "unverified_count": 0,
                "unverified_numbers": [],
                "extracted_numbers": [],
                "bundle_values": []
            }

        extracted = cls._extract_numbers_from_text(brief_text)
        bundle_values = cls._extract_all_bundle_values(evidence_bundle)

        unverified_numbers = []
        for num in extracted:
            # Skip allowed constants (common helpers, years)
            if num in cls.ALLOWED_CONSTANTS:
                continue

            # Check against every value in the bundle
            matched = any(cls._numbers_match(num, b_val) for b_val in bundle_values)

            if not matched:
                unverified_numbers.append(num)

        is_valid = len(unverified_numbers) == 0

        return {
            "verified": is_valid,
            "unverified_count": len(unverified_numbers),
            "unverified_numbers": sorted(set(unverified_numbers)),
            "extracted_numbers": sorted(set(extracted)),
            "bundle_values": sorted(bundle_values)
        }


verification_engine = VerificationEngine()
