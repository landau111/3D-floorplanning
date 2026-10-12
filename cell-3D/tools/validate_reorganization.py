"""Compare a full rerun with the untouched published output and source snapshot."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path)
    args=parser.parse_args()
    latest=json.loads((ROOT/"results/latest.json").read_text(encoding="utf-8"))
    run=args.run or ROOT/"results"/latest["path"]
    old=ROOT/"results/2026-10-13/20261013_release"
    manifest=json.loads((old/"manifest.json").read_text(encoding="utf-8"))
    snapshot=ROOT/"archive/source_snapshots/2026-10-13/published_flat"
    hashes={name:sha(snapshot/name)==digest for name,digest in manifest["source_sha256"].items()}
    assert all(hashes.values()),hashes
    inputs={name:sha(run/name)==sha(old/name) for name in ("input_config.yaml.json","input_annealing_cfg.yaml")}
    assert all(inputs.values()),inputs
    arrays={}
    for profile in ("initial","balanced","timing","thermal"):
        a,b=np.load(old/(profile+".npz")),np.load(run/(profile+".npz"))
        arrays[profile]={key:bool(np.array_equal(a[key],b[key])) for key in a.files}
        assert all(arrays[profile].values()),arrays[profile]
    metrics=sha(old/"metrics.csv")==sha(run/"metrics.csv")
    assert metrics,"Performance metrics changed"
    baseline_tree=ast.parse((snapshot/"run_layout.py").read_text(encoding="utf-8-sig"))
    current_tree=ast.parse((ROOT/"src/run_layout.py").read_text(encoding="utf-8-sig"))
    names=("Heat","Model","Regions","Cells","Routing","pareto","source_settings")
    get=lambda tree:{n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef))}
    x,y=get(baseline_tree),get(current_tree)
    kernels={name:x[name]==y[name] for name in names}
    assert all(kernels.values()),kernels
    report=dict(reference_run=old.relative_to(ROOT).as_posix(),rerun=run.relative_to(ROOT).as_posix(),
                unchanged_published_source_hashes=hashes,identical_input_bytes=inputs,identical_npz_arrays=arrays,
                identical_metrics_csv_bytes=metrics,unchanged_algorithm_AST=kernels,
                backend="HotSpot",unit_tests=11,notes="evaluate only changes baseline path; main adds dated results and indexing. No optimization math change.")
    (ROOT/"docs/REORGANIZATION_VALIDATION.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("PASS: source provenance, input bytes, all four profiles' arrays and metrics unchanged")

if __name__=="__main__":main()
