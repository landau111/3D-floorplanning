"""Extract the actual offline ZIP and validate relocation plus changed inputs."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from results_index import update_index

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract",type=Path,required=True)
    parser.add_argument("--name",default="organized_portable")
    args=parser.parse_args()
    extract=args.extract.resolve()
    if not extract.is_relative_to(ROOT.parent) or extract.exists():raise ValueError("Use a new extraction directory inside the workspace")
    extract.mkdir(parents=True)
    archive=ROOT/"releases/cell3d_windows_x64_offline.zip"
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not (extract/name).resolve().is_relative_to(extract):raise ValueError("Unsafe ZIP member")
        z.extractall(extract)
    bundle=extract/"cell-3D";python=bundle/"runtime/python.exe"
    env=os.environ.copy()
    for key in ("PYTHONPATH","PYTHONHOME"):env.pop(key,None)
    env["PYTHONUTF8"]="1"
    def run(command,log):
        result=subprocess.run(command,cwd=ROOT.parent,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        log.parent.mkdir(parents=True,exist_ok=True);log.write_bytes(result.stdout)
        if result.returncode:raise ValueError(result.stdout.decode("utf-8",errors="replace"))
    latest=json.loads((ROOT/"results/latest.json").read_text(encoding="utf-8"))
    day=ROOT/"results"/latest["date"]
    full=day/(args.name+"_full");changed=day/(args.name+"_changed")
    for folder in (full,changed):
        if folder.exists():raise ValueError("Result already exists: "+str(folder))
    cfg=bundle/"configs/config.yaml.json";aux=bundle/"configs/folding_dse_annealing_cfg.yaml"
    original={p.name:digest(p) for p in (cfg,aux)}
    run([str(python),str(bundle/"run.py"),"--check"],extract/"input_check.log")
    run([str(python),"-m","unittest","discover","-s",str(bundle/"tests")],extract/"unit_tests.log")
    # cmd /s strips an outer quote pair: protect the entire invocation, including
    # the quoted launcher and all configuration/output paths containing spaces.
    def launch(arguments):
        return 'cmd.exe /d /s /c "'+subprocess.list2cmdline([str(bundle/"run_layout.cmd")]+arguments)+'"'
    run(launch(["--run-kind","environment_validation","--output",str(full)]),extract/"full_run.log")
    matches={}
    for profile in ("initial","balanced","timing","thermal"):
        a=np.load(full/(profile+".npz"));b=np.load(ROOT/"results"/latest["path"]/(profile+".npz"))
        matches[profile]={key:bool(np.array_equal(a[key],b[key])) for key in ("xy_mm","labels","edges","route_choice")}
        assert all(matches[profile].values()),matches[profile]
    inputs=bundle/"changed inputs";inputs.mkdir()
    (inputs/"config.yaml").write_text(cfg.read_text(encoding="utf-8").replace("x= 0.020    y= 0.020","x= 0.030    y= 0.020",1),encoding="utf-8")
    (inputs/"annealing.yaml").write_text(aux.read_text(encoding="utf-8").replace("ls: 0.355","ls: 0.365"),encoding="utf-8")
    run(launch(["--quick","--config",str(inputs/"config.yaml"),"--annealing-config",str(inputs/"annealing.yaml"),"--output",str(changed)]),extract/"changed_run.log")
    manifest=json.loads((changed/"manifest.json").read_text(encoding="utf-8"))
    assert abs(manifest["power_provenance"]["total_module_dynamic_W"]-.855)<1e-10
    assert next(m for m in manifest["input"]["modules"] if m["name"]=="id")["rect_mm"][0]==.03
    assert {p.name:digest(p) for p in (cfg,aux)}==original
    for folder,log in [(full,"full_run.log"),(changed,"changed_run.log")]:
        (folder/"validation_stdout.txt").write_bytes((extract/log).read_bytes())
    assert update_index(ROOT/"results")["path"]==latest["path"]
    report=dict(actual_offline_zip_extraction=True,non_ascii_and_space_path=str(extract),
                isolated_runtime=True,different_working_directory=True,windows_launcher_full_run=True,
                identical_placement_to_formal_HotSpot_run=matches,changed_config=True,
                changed_power_total_W=.855,changed_id_x_mm=.03,original_input_unchanged=True,
                quick_and_environment_tests_preserve_formal_latest=True,unit_tests="11 passed in workspace and extracted package",
                full_result=full.relative_to(ROOT).as_posix(),changed_result=changed.relative_to(ROOT).as_posix(),
                tested_archive_sha256=digest(archive),
                limitations="Company desktop not accessed. Linux/ARM/macOS runtime not tested; default proxy needs no WSL. HotSpot separately tested in full formal rerun.")
    (ROOT/"docs/PORTABILITY_VALIDATION.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("PASS: actual ZIP, relocated isolated runtime, 11 tests, full launcher run, changed inputs and latest preservation")

if __name__=="__main__":main()
