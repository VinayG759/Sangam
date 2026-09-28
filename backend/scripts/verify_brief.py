"""
Check a Sangam brief offline, with no server and no database.

    python -m scripts.verify_brief path/to/brief.pdf [path/to/public-key-file]

The public key defaults to docs/brief-signing-key.pub in this repository.
Exit code 0 means the brief is exactly as Sangam exported it.
"""

import sys
from pathlib import Path

from app.core.signing import VALID, verify_pdf

DEFAULT_KEY = Path(__file__).resolve().parents[2] / "docs" / "brief-signing-key.pub"

MESSAGES = {
    "valid": "VALID: signed by Sangam and unchanged since export.",
    "tampered": "TAMPERED: the file was changed after it was signed.",
    "unsigned": "UNSIGNED: no Sangam signature found (never signed, or re-saved by another program).",
    "other_key": "OTHER KEY: signed by a key other than the published Sangam key.",
}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    key_file = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_KEY
    public_key = next(line.strip() for line in key_file.read_text().splitlines()
                      if line.strip() and not line.startswith("#"))
    result = verify_pdf(Path(sys.argv[1]).read_bytes(), public_key)
    print(MESSAGES[result.status])
    return 0 if result.status == VALID else 1


if __name__ == "__main__":
    sys.exit(main())
