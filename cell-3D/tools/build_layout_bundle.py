"""Build reproducible source / Windows x64 runtime bundles (maintainer utility)."""
import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
FILES=["README.md","run.py","run_layout.cmd","run_layout.sh","requirements.txt"]


def zip_folder(folder,destination,include_runtime=True):
    with zipfile.ZipFile(destination,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file in sorted(folder.rglob("*")):
            relative=file.relative_to(folder)
            if not include_runtime and relative.parts[0]=="runtime":continue
            if file.is_file() and "__pycache__" not in file.parts:
                archive.write(file,(Path("cell-3D")/file.relative_to(folder)).as_posix())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--python-runtime",type=Path,required=True)
    parser.add_argument("--stage",type=Path,required=True)
    parser.add_argument("--releases",type=Path,default=HERE/"releases")
    parser.add_argument("--refresh",action="store_true",help="Refresh a previously built, unmodified staging folder")
    args=parser.parse_args();stage=args.stage.resolve()
    if not stage.is_relative_to(HERE.parent):raise ValueError("Stage must be inside the workspace")
    if stage.exists():
        if not args.refresh:raise ValueError("Use a new stage directory or --refresh; nothing is deleted")
        checks=json.loads((stage/"BUNDLE_MANIFEST.json").read_text(encoding="utf-8"))["files"]
        for name,digest in checks.items():
            if hashlib.sha256((stage/name).read_bytes()).hexdigest()!=digest:raise ValueError("Staging file was modified: "+name)
    else:stage.mkdir(parents=True)
    args.releases.mkdir(parents=True,exist_ok=True)
    for name in FILES:shutil.copy2(HERE/name,stage/name)
    for name in ("src","configs","data","tests","docs","tools"):
        shutil.copytree(HERE/name,stage/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    for name in ("archive","releases"):
        (stage/name).mkdir(exist_ok=True)
        shutil.copy2(HERE/name/"README.md",stage/name/"README.md")
    latest=json.loads((HERE/"results/latest.json").read_text(encoding="utf-8"))
    for relative in (latest["path"],"2026-10-13/20261013_release"):
        shutil.copytree(HERE/"results"/relative,stage/"results"/relative,dirs_exist_ok=True)
    # Portable bundles contain the current and published reference results only.
    sys.path.insert(0,str(HERE/"src"))
    from results_index import update_index
    records=json.loads((HERE/"results/catalog.json").read_text(encoding="utf-8"))
    subset=[dict(r,path="results/"+r["path"]) for r in records if (stage/"results"/r["path"]).is_dir()]
    (stage/"results/history_catalog.json").write_text(json.dumps(subset,ensure_ascii=False,indent=2),encoding="utf-8")
    update_index(stage/"results")
    (stage/"PACKAGE_CONTENTS.md").write_text("# 便携包范围\n\n此包包含当前源码、配置、测试、文档、最新正式结果及发布参考结果；全部历史代码与历史实验请查看 GitHub 的 archive 和 results 目录。\n",encoding="utf-8")
    third=HERE.parent/"third_party/HotSpot"
    if not third.is_dir():third=HERE/"third_party/HotSpot"
    target=stage/"third_party/HotSpot";target.mkdir(parents=True,exist_ok=True)
    for file in third.iterdir():
        if file.suffix in (".c",".h",".config",".md") or file.name in ("LICENSE","Makefile"):
            shutil.copy2(file,target/file.name)
    checks={str(p.relative_to(stage).as_posix()):hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob("*") if p.is_file() and p.name!="BUNDLE_MANIFEST.json" and p.relative_to(stage).parts[0]!="runtime"}
    (stage/"BUNDLE_MANIFEST.json").write_text(json.dumps(dict(files=checks,python_runtime="added in Windows archive only",hotspot="source; optional"),indent=2),encoding="utf-8")
    source=args.releases/"cell3d_source.zip";zip_folder(stage,source,False)
    runtime=args.python_runtime.resolve();dest=stage/"runtime"
    if dest.exists():
        offline=args.releases/"cell3d_windows_x64_offline.zip";zip_folder(stage,offline)
        result={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (source,offline)}
        (args.releases/"SHA256.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        print(json.dumps(result,indent=2));return
    dest.mkdir()
    for file in runtime.iterdir():
        if file.is_file() and (file.suffix in (".exe",".dll") or file.name=="LICENSE.txt"):
            shutil.copy2(file,dest/file.name)
    ignore=shutil.ignore_patterns("site-packages","__pycache__","test","tests","idlelib","tkinter")
    shutil.copytree(runtime/"Lib",dest/"Lib",ignore=ignore)
    shutil.copytree(runtime/"DLLs",dest/"DLLs")
    (dest/"Lib/site-packages").mkdir()
    for file in (runtime/"Lib/site-packages").iterdir():
        if file.name in ("numpy","numpy.libs") or file.name.startswith("numpy-") and file.name.endswith(".dist-info"):
            shutil.copytree(file,dest/"Lib/site-packages"/file.name,ignore=shutil.ignore_patterns("__pycache__"))
    (dest/"python312._pth").write_text(".\n..\nLib\nDLLs\nLib/site-packages\nimport site\n",encoding="ascii")
    offline=args.releases/"cell3d_windows_x64_offline.zip";zip_folder(stage,offline)
    result={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (source,offline)}
    (args.releases/"SHA256.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
