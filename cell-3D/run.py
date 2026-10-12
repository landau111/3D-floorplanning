"""Public entry point; all implementation is in src/."""
import runpy
import sys
from pathlib import Path

if __name__=="__main__":
    source=Path(__file__).resolve().parent/"src"
    sys.path.insert(0,str(source))
    runpy.run_path(str(source/"run_layout.py"),run_name="__main__")
