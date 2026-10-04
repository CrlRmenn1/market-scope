"""Filesystem locations of the backend's data files."""
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
PBF_PATH = DATA_DIR / "panabo.pbf"
