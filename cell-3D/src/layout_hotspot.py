"""Optional final HotSpot evaluation; portable optimizer itself needs only NumPy."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
import numpy as np


def linux_path(path):
    value=Path(path).resolve().as_posix()
    return "/mnt/"+value[0].lower()+value[2:] if len(value)>2 and value[1]==":" else value


def run_hotspot_grid(d,pmap,folder,executable=None,wsl=None):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    aux=d.aux;stack=aux["stack"]
    if not stack or not aux["hotspot"]:raise ValueError("HotSpot requires stack and hotspot in annealing config")
    rows,cols=aux["thermal_grid_rows"],aux["thermal_grid_cols"]
    if rows!=cols:raise ValueError("Current cell temperature interpolation requires square HotSpot grid counts (die can be rectangular)")
    g=d.heat.g;dx,dy=d.extent/g;names=[];watts=[]
    for z,tier in enumerate(("bottom","top")):
        flp=[]
        for y in range(g):
            for x in range(g):
                name="{}_{}_{}".format(tier,y,x);names.append(name);watts.append(float(pmap[z*g*g+y*g+x]))
                flp.append("{} {:.15g} {:.15g} {:.15g} {:.15g}".format(name,dx*1e-3,dy*1e-3,x*dx*1e-3,y*dy*1e-3))
        (folder/(tier+".flp")).write_text("\n".join(flp)+"\n",encoding="ascii")
    lcf=[];mapping={}
    for index,v in reversed(list(enumerate(stack))):
        powered=v["power_layer"]!="none";name=v["power_layer"] if powered else v["name"]
        if powered:mapping[name]=index
        else:(folder/(name+".flp")).write_text("{} {:.15g} {:.15g} 0 0\n".format(name,d.extent[0]*1e-3,d.extent[1]*1e-3),encoding="ascii")
        lcf.extend([str(index),"Y","Y" if powered else "N",str(v["heat_capacity_J_m3_K"]),str(1/v["conductivity_W_m_K"]),str(v["thickness_um"]*1e-6),name+".flp"])
    (folder/"stack.lcf").write_text("\n".join(lcf)+"\n",encoding="ascii")
    (folder/"power.ptrace").write_text(" ".join(names)+"\n"+" ".join("{:.15g}".format(v) for v in watts)+"\n",encoding="ascii")
    parameters=dict(aux["hotspot"])
    parameters.update(model_type="grid",detailed_3D="on",grid_rows=rows,grid_cols=cols,
        ambient=d.settings["ambient_C"]+273.15,init_temp=d.settings["ambient_C"]+273.15,
        model_secondary=0,leakage_used=0,package_model_used=0,grid_map_mode="max",use_microfluidic_cooling=0)
    (folder/"hotspot.config").write_text("\n".join("-{} {}".format(k,v) for k,v in sorted(parameters.items()))+"\n",encoding="ascii")
    here=Path(__file__).resolve().parent
    bundled=next((p for p in (here.parent/"third_party/HotSpot/hotspot",here.parent.parent/"third_party/HotSpot/hotspot") if p.is_file()),here.parent/"third_party/HotSpot/hotspot")
    exe=executable or os.environ.get("HOTSPOT_EXE") or shutil.which("hotspot") or str(bundled)
    args=["-c","hotspot.config","-grid_layer_file","stack.lcf","-f","bottom.flp","-p","power.ptrace","-steady_file","hotspot.steady","-grid_steady_file","hotspot.grid.steady"]
    if wsl:
        command=["wsl.exe","-d",wsl,"--cd",linux_path(folder),"--exec",linux_path(exe)]+args
    else:command=[exe]+args
    run=subprocess.run(command,cwd=str(folder),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
    (folder/"stdout.txt").write_bytes(run.stdout);(folder/"stderr.txt").write_bytes(run.stderr)
    if run.returncode:raise ValueError("HotSpot failed {}: {}".format(run.returncode,run.stderr.decode("utf-8",errors="replace")[-1000:]))
    fields={};current=None
    for line in (folder/"hotspot.grid.steady").read_text(encoding="ascii").splitlines():
        if line.startswith("Layer "):
            current=int(line.split()[1].rstrip(":"));fields[current]={}
        elif line.strip():
            k,t=line.split();fields[current][int(k)]=float(t)-273.15
    maps=[]
    for tier in ("bottom","top"):
        field=fields[mapping[tier]]
        if len(field)!=rows*cols:raise ValueError("Incomplete HotSpot grid")
        maps.append(np.array([field[k] for k in range(rows*cols)]).reshape(rows,cols)[::-1])
    result=np.array(maps).ravel()
    if not np.isfinite(result).all() or result.min()<d.settings["ambient_C"]-.02:raise ValueError("Invalid HotSpot temperatures")
    info=dict(command=command,total_power_W=sum(watts),power_conservation_error_W=abs(sum(watts)-pmap.sum()),
        nominal_peak_C=float(result.max()),grid=[cols,rows],backend="HotSpot",stack=stack,package=aux["hotspot"],
        executable_sha256=hashlib.sha256(Path(exe).read_bytes()).hexdigest() if Path(exe).is_file() else None)
    (folder/"manifest.json").write_text(json.dumps(info,indent=2),encoding="utf-8")
    return result
