"""Render the reviewed vector figure book to stable PNG filenames."""
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
out = ROOT/"figures"
m = json.loads((out/"figure_manifest.json").read_text(encoding="utf-8"))
pdf = ROOT/"output/pdf/cell3d_layouts_and_pareto.pdf"
bundled = Path.home()/".cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe"
exe = shutil.which("pdftoppm") or (str(bundled) if bundled.exists() else None)
if exe:
    subprocess.run([exe, "-r", "144", "-png", str(pdf), str(out/"rendered")], check=True)
    for i, name in enumerate(m["pages"], 1):
        shutil.copyfile(out/f"rendered-{i}.png", out/f"{name}.png")
else:
    import pypdfium2
    doc = pypdfium2.PdfDocument(str(pdf))
    for i, name in enumerate(m["pages"]):
        doc[i].render(scale=2).to_pil().save(out/f"{name}.png")
print("Rendered", len(m["pages"]), "PNG figures at 2400×1800 px")
