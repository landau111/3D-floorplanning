"""Rebuild all result READMEs and the latest formal result entry."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from results_index import update_index
if __name__ == "__main__":
    print(update_index(ROOT / "results"))
