"""Entry point for `python -m xujin_workflow`."""
from __future__ import annotations

import sys

from . import executor


def main() -> int:
    return executor.main()


if __name__ == "__main__":
    sys.exit(main())
