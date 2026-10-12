"""Replay legacy code in a new dated directory, preserving original history."""
import argparse
import datetime
import shutil
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from results_index import allocate_output,update_index,write_json,ZONE

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("test-model","test-puzzle","simulate","puzzle"))
    parser.add_argument("--output",type=Path)
    args,extra=parser.parse_known_args()
    out=allocate_output(ROOT/"results",args.output)
    work=out/"work/legacy"
    shutil.copytree(ROOT/"archive/legacy",work)
    baseline=work.parent/"gem5-c910-baseline/results";baseline.mkdir(parents=True)
    shutil.copy2(work/"gem5_stats.json",baseline/"stats.json")
    for source,target in [("rectangular","results"),("puzzle","puzzle_results")]:
        shutil.copytree(ROOT/"results/2026-09-25"/source,work/target)
    info=dict(kind="legacy_replay",status="running",started_at=datetime.datetime.now(ZONE).isoformat(),action=args.action)
    write_json(out/"run_info.json",info)
    script={"test-model":"test_model.py","test-puzzle":"test_puzzle.py","simulate":"simulate.py","puzzle":"puzzle.py"}[args.action]
    command=[sys.executable,str(work/script)]+extra
    if args.action=="simulate":command += ["--output",str(work/"replay_results")]
    result=subprocess.run(command,cwd=work)
    info["status"]="complete" if result.returncode==0 else "failed"
    write_json(out/"run_info.json",info);update_index(ROOT/"results")
    print("Archived replay:",out)
    return result.returncode

if __name__=="__main__":raise SystemExit(main())
