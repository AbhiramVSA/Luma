"""Shared test fixtures and path setup."""

import sys
from pathlib import Path

# Add src/ to the Python path so tests can import backend modules directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
