"""Entry point for the Hydra CLI when run as a module."""

import sys

from hydra.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
