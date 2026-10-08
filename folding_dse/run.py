"""Simple entry points shared by Makefile and the Windows launcher."""

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import shutil
import sys


HERE = Path(__file__).resolve().parent


def windows_wsl():
    """Use the already installed Linux toolchain when no Windows HotSpot exists."""
    if sys.platform != "win32" or "--dry-run" in sys.argv or (len(sys.argv)>1 and sys.argv[1] in ("test","help")):
        return None
    if "--hotspot-exe" in sys.argv or os.environ.get("HOTSPOT_EXE") or shutil.which("hotspot.exe"):
        return None
    if not shutil.which("wsl.exe"):
        raise RuntimeError("HotSpot requires a C compiler. Use Linux/WSL, or provide --hotspot-exe for a Windows build.")
    result = subprocess.run(["wsl.exe","--list","--quiet"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    names = result.stdout.decode("utf-16-le").replace("\x00", "").splitlines()
    names = [n.strip() for n in names if n.strip() and "docker" not in n.lower()]
    distro = os.environ.get("FOLDING_DSE_WSL_DISTRO") or next((n for n in names if n.startswith("Codex-")), names[0] if names else None)
    if not distro:
        raise RuntimeError("No usable WSL distribution. Run on CentOS/Linux or install a WSL distribution.")
    def linux_path(value):
        path = Path(value).resolve().as_posix()
        if len(path)>2 and path[1] == ':':
            return '/mnt/'+path[0].lower()+path[2:]
        return value
    arguments = sys.argv[1:]
    for i,arg in enumerate(arguments[:-1]):
        if arg in ("--config","--output"):
            arguments[i+1] = linux_path(arguments[i+1])
    cwd = linux_path(str(HERE.parent))
    prefix = ["wsl.exe","-d",distro,"--cd",cwd,"--exec"]
    print("Using WSL distribution: " + distro,flush=True)
    build = subprocess.run(prefix+["make","hotspot"])
    if build.returncode:
        return build.returncode
    if arguments and arguments[0] == "hotspot":
        return 0
    return subprocess.run(prefix+["python3","folding_dse/run.py"]+arguments).returncode


def main() -> int:
    if sys.version_info < (3, 6):
        print("Python 3.6 or newer is required.", file=sys.stderr)
        return 2
    forwarded = windows_wsl()
    if forwarded is not None:
        return forwarded
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="explore",
                        choices=("explore", "quick", "optimize", "test", "test-hotspot", "help", "hotspot"))
    parser.add_argument("--config", type=Path, default=HERE / "folding_dse_annealing_cfg.yaml")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--steps", type=int)
    parser.add_argument("--restarts", type=int)
    parser.add_argument("--selected", type=int, default=4)
    parser.add_argument("--hotspot-exe")
    parser.add_argument("--thermal-rounds",type=int)
    parser.add_argument("--profiles")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.action == "hotspot":
        return subprocess.run(["make","-C",str(HERE.parent/"third_party/HotSpot"),"hotspot","SUPERLU=0","VERBOSE=0","EXTRAFLAGS=-std=gnu99"]).returncode
    if args.action == "help":
        print("explore : Pareto search and layout/temperature maps (default)")
        print("quick   : Small search to check the workflow")
        print("optimize: One selected layout with configured weights and HotSpot")
        print("hotspot : Compile the bundled official HotSpot source")
        print("test    : Run behavioral checks")
        parser.print_help()
        return 0

    command = [sys.executable, "-u"]
    if args.action in ("test", "test-hotspot"):
        if args.action == "test-hotspot":
            os.environ["REQUIRE_HOTSPOT_TEST"] = "1"
        command.append(str(HERE / "test_optimize.py"))
        output = None
    else:
        quick = args.action == "quick"
        single = args.action == "optimize"
        default = HERE/("quick_results" if quick else "single_results" if single else "local_results")
        if args.output is None and (default/"manifest.json").exists():
            from datetime import datetime
            default = HERE/(default.name+"_"+datetime.now().strftime("%Y%m%d_%H%M%S"))
        output = (args.output or default).resolve()
        command += [str(HERE/"explore.py"),str(args.config.resolve()),"--output",str(output),
                    "--selected",str(1 if single else args.selected)]
        for name,value in (("steps",args.steps if args.steps is not None else (500 if quick else None)),
                           ("restarts",args.restarts if args.restarts is not None else (1 if quick else None)),
                           ("thermal-rounds",args.thermal_rounds if args.thermal_rounds is not None else (3 if quick else None)),
                           ("profiles","balanced" if single else args.profiles),
                           ("hotspot-exe",str(Path(args.hotspot_exe).resolve()) if args.hotspot_exe else None)):
            if value is not None:
                command += ["--"+name,str(value)]

    print(subprocess.list2cmdline(command) if sys.platform == "win32" else
          " ".join(shlex.quote(part) for part in command), flush=True)
    if args.dry_run:
        return 0
    result = subprocess.run(command, cwd=HERE.parent)
    if result.returncode == 0 and output is not None:
        print(f"Results: {output}", flush=True)
        print(f"Open: {output / 'pareto.svg'}", flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
