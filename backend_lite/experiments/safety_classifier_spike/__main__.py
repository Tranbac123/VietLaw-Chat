"""Print aggregate-only offline spike evidence."""

from __future__ import annotations

import json

from .harness import offline_summary


def main() -> None:
    print(json.dumps(offline_summary(), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
