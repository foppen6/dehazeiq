"""Ingångsskript för PyInstaller (den installerade appen)."""

import multiprocessing
import sys

from dehazeiq.launcher import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
