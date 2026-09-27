"""
Command line for country packs.

    python -m app.features.packs validate india
    python -m app.features.packs load india
"""

import sys

from app.core.db import new_session
from app.features.packs.load import load_pack_into_db
from app.features.packs.validate import validate_pack


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in {"validate", "load"}:
        print(__doc__)
        return 2
    command, name = argv
    if command == "validate":
        problems = validate_pack(name)
        for problem in problems:
            print(f"  ✗ {problem}")
        print(f"{name}: {'INVALID' if problems else 'valid'}" + (f" ({len(problems)} problems)" if problems else ""))
        return 1 if problems else 0
    with new_session() as db:
        counts = load_pack_into_db(db, name)
    print(f"{name}: loaded {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
