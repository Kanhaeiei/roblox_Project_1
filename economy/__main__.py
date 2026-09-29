"""Main entrypoint for python -m economy."""

import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
