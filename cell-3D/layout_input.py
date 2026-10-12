"""Read the user's layout-summary text without YAML/JSON dependencies."""
import hashlib
import math
import re
from pathlib import Path

ALIASES = {"if_ctrl": "if_ctl", "l2_ctrl": "l2_ctl"}


def canonical(name):
    return ALIASES.get(name, name)


def read_layout(path):
    path = Path(path)
    raw_bytes = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            raw = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            pass
    else:
        raise ValueError("Config must be UTF-8 or GB18030 text")
    number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
    layers, declared = {}, {}
    for label, count, names in re.findall(r"\b(BOT|TOP)\s*\((\d+)\)\s*:\s*([^\r\n]+)", raw):
        names = [canonical(n.strip()) for n in re.split(r"[,，]", names) if n.strip()]
        if label in declared or len(names) != int(count):
            raise ValueError("Invalid partition count or repeated partition: " + label)
        declared[label] = names
        for name in names:
            if name in layers:
                raise ValueError("Repeated module in partition: " + name)
            layers[name] = 0 if label == "BOT" else 1
    if set(declared) != {"BOT", "TOP"}:
        raise ValueError("Expected Partition BOT(n): ... and TOP(n): ...")
    rects, hard, temps = {}, set(), {}
    section, current_tier = None, None
    for line in raw.splitlines():
        if "Final placement coordinates" in line:
            section = "rects"
        elif "Module steady-state temps" in line:
            section = "temps"
        elif "Key parameters" in line:
            section = "parameters"
        if section == "rects":
            tier_match = re.fullmatch(r"\s*(BOT|TOP)\s*:\s*", line)
            if tier_match:
                current_tier = 0 if tier_match[1] == "BOT" else 1
            match = re.match(r"\s*([A-Za-z_]\w*)\s+x\s*=", line)
            if match:
                name = canonical(match[1])
                values = {}
                for key, value in re.findall(r"\b([xywh])\s*=\s*(" + number + ")", line):
                    if key in values:
                        raise ValueError("Repeated coordinate " + key + " for " + name)
                    values[key] = float(value)
                if set(values) != set("xywh") or name in rects:
                    raise ValueError("Missing/repeated x,y,w,h: " + name)
                if name not in layers or layers[name] != current_tier:
                    raise ValueError("Coordinates disagree with partition: " + name)
                rects[name] = [values[k] for k in "xywh"]
                if "硬模块" in line or "hard" in line.lower():
                    hard.add(name)
        elif section == "temps":
            match = re.match(r"\s*([A-Za-z_]\w*)\s*(?:=|:)\s*(" + number + r")\s*(?:°?C)?\s*$", line)
            if match:
                name = canonical(match[1])
                if name in temps:
                    raise ValueError("Repeated module temperature: " + name)
                temps[name] = float(match[2])
    if set(rects) != set(layers) or set(temps) != set(layers):
        raise ValueError("Every partition module must have coordinates and temperature; missing rects {} / temps {}".format(
            sorted(set(layers)-set(rects)), sorted(set(layers)-set(temps))))
    def required(pattern, name):
        match = re.search(pattern, raw, re.IGNORECASE)
        if not match:
            raise ValueError("Missing input parameter: " + name)
        return match
    die = required(r"die\s+W\s*x\s*H\s*=\s*("+number+r")\s*x\s*("+number+r")", "die W x H")
    width, height = float(die[1]), float(die[2])
    area = float(required(r"\barea_limit\s*=\s*("+number+r")", "area_limit")[1])
    pitch = float(required(r"\bHBT\s+pitch\s*=\s*("+number+r")", "HBT pitch")[1])
    vertical = float(required(r"\bhbt_vert\s*=\s*("+number+r")", "hbt_vert")[1])
    density = float(required(r"上限\s*("+number+r")\s*/mm", "HBT density limit")[1])
    spill = float(required(r"\bspill_coef\s*=\s*("+number+r")", "spill_coef")[1])
    penalty = float(required(r"\bviol_penalty_coef\s*=\s*("+number+r")", "viol_penalty_coef")[1])
    hbt_count = int(required(r"\bHBT\s*=\s*(\d+)", "HBT reference count")[1])
    peak = float(required(r"\bPeakTemp\s*=\s*("+number+r")", "PeakTemp")[1])
    values = [width,height,area,pitch,vertical,density,spill,penalty,peak]+list(temps.values())
    if not all(math.isfinite(v) for v in values) or min(width,height,area,pitch,density)<=0 or min(spill,penalty,vertical)<0:
        raise ValueError("Invalid physical dimensions or non-finite parameter")
    if density > (1000/pitch)**2+1e-6:
        raise ValueError("HBT density exceeds geometric pitch capacity")
    if hbt_count > math.floor(width/pitch*1000)*math.floor(height/pitch*1000):
        raise ValueError("Reference HBT count exceeds total pitch sites")
    layer_areas = [0.0,0.0]
    for name, (x,y,w,h) in rects.items():
        if not all(math.isfinite(v) for v in (x,y,w,h)) or min(x,y)<-1e-9 or min(w,h)<=0 or x+w>width+1e-9 or y+h>height+1e-9:
            raise ValueError("Module outside die or invalid rectangle: " + name)
        layer_areas[layers[name]] += w*h
    if max(layer_areas)>area+1e-8:
        raise ValueError("Initial module areas exceed area_limit: " + str(layer_areas))
    for i,a in enumerate(rects):
        x,y,w,h=rects[a]
        for b in list(rects)[i+1:]:
            if layers[a] != layers[b]:
                continue
            xx,yy,ww,hh=rects[b]
            if min(x+w,xx+ww)>max(x,xx)+1e-9 and min(y+h,yy+hh)>max(y,yy)+1e-9:
                raise ValueError("Overlapping initial modules: {} / {}".format(a,b))
    # Summary values describe the supplied initial point; never trust PASS as validation.
    area_match = re.search(r"Layer area:\s*BOT\s*=\s*("+number+r").*?TOP\s*=\s*("+number+r")",raw)
    warnings=[]
    if area_match:
        expected=[float(area_match[1]),float(area_match[2])]
        if any(abs(a-b)>0.001 for a,b in zip(expected,layer_areas)):
            warnings.append("Layer area summary differs from coordinates; using coordinates")
    if abs(max(temps.values())-peak)>0.1:
        warnings.append("PeakTemp differs from module temperatures; reference values retained")
    return dict(schema="layout-summary-text-v1", width_mm=width,height_mm=height,area_limit_mm2=area,
        modules=[dict(name=n,tier=layers[n],rect_mm=rects[n],hard=n in hard,reference_C=temps[n]) for n in layers],
        pitch_um=pitch,hbt_vertical_um=vertical,max_density_per_mm2=density,
        spill_coef=spill,viol_penalty_coef=penalty,reference_hbt_count=hbt_count,reference_peak_C=peak,
        initial_layer_area_mm2=layer_areas,warnings=warnings,input_sha256=hashlib.sha256(raw_bytes).hexdigest())


def read_auxiliary(path, layout):
    """Read physics/connectivity from annealing YAML; layout owns geometry/tier."""
    from yaml_subset import _parse_compact_yaml
    data_bytes=Path(path).read_bytes()
    raw=data_bytes.decode("utf-8-sig")
    try:
        import json
        data=json.loads(raw)
    except ValueError:
        data=_parse_compact_yaml(raw)
    names={m["name"] for m in layout["modules"]}
    aliases={"mmu":"mm"} if "mm" in names and "mmu" not in names else {}
    def name(n):return aliases.get(canonical(n),canonical(n))
    if "power_w" in data:
        powers={name(n):float(v) for n,v in data["power_w"].items()}
    elif "modules" in data:
        powers={name(n):float(v["power_w"]) for n,v in data["modules"].items()}
    else:raise ValueError("Annealing config must contain power_w")
    if set(powers)!=names or any(not math.isfinite(p) or p<0 for p in powers.values()):
        raise ValueError("Power modules must exactly match final layout modules")
    if len(data.get("power_w",data.get("modules",{})))!=len(powers):
        raise ValueError("Repeated power module after alias normalization")
    links=[];seen=set()
    for a,b,n in data.get("interconnect",[]):
        a,b=name(a),name(b)
        if a not in names or b not in names or a==b or not isinstance(n,int) or n<=0:
            raise ValueError("Invalid annealing interconnect: "+str([a,b,n]))
        pair=tuple(sorted((a,b)))
        if pair in seen:raise ValueError("Repeated interconnect pair: "+str(pair))
        seen.add(pair);links.append([a,b,n])
    if not links:raise ValueError("Annealing config must contain interconnect")
    layers={m["name"]:m["tier"] for m in layout["modules"]}
    cross=sum(n for a,b,n in links if layers[a]!=layers[b])
    warnings=[]
    if cross!=layout["reference_hbt_count"]:
        warnings.append("Layout summary HBT={} vs supplied cross-tier signals={}; using supplied connectivity without scaling".format(layout["reference_hbt_count"],cross))
    supplied_density=data.get("hbt",{}).get("max_density_per_mm2",data.get("max_density_per_mm2"))
    if supplied_density is not None and supplied_density!=layout["max_density_per_mm2"]:
        warnings.append("Density limit differs: layout {} vs annealing {}; layout wins".format(layout["max_density_per_mm2"],supplied_density))
    constraints=[]
    for item in data.get("layout_constrains",[]):
        item=dict(item);item["pair"]=[name(n) for n in item["pair"]]
        if "layer" in item:item["layer"]=item["layer"].upper()
        if any(n not in names for n in item["pair"]):raise ValueError("Unknown constraint module")
        if len(item["pair"])!=2 or not math.isfinite(float(item["max_dist_mm"])) or item["max_dist_mm"]<=0:
            raise ValueError("Invalid soft distance constraint")
        if item.get("layer","") not in ("","BOT","TOP"):raise ValueError("Invalid soft tier preference")
        constraints.append(item)
    if not 0<=float(data.get("bond_reserve_fraction",.2))<1:raise ValueError("bond_reserve_fraction must be in [0,1)")
    if float(data.get("bond_window_mm",.1))<=0 or float(data.get("module_gap_mm",.008))<0:raise ValueError("Invalid bond window or module gap")
    return dict(power_w=powers,interconnect=links,cross_tier_signal_count=cross,
        ambient_c=float(data.get("ambient_c",26.85)),timing=data.get("timing",{}),
        bond_window_mm=float(data.get("bond_window_mm",.1)),
        bond_reserve_fraction=float(data.get("bond_reserve_fraction",.2)),
        module_gap_mm=float(data.get("module_gap_mm",.008)),
        rc_temp_alpha=float(data.get("rc_temp_alpha",.0039)),rc_ref_temp=float(data.get("rc_ref_temp",27)),
        critical_modules=[name(n) for n in data.get("critical_modules",[])],
        net_weights=data.get("net_weights",{}),objective_weights=data.get("objective_weights",{}),
        layout_constraints=constraints,stack=data.get("stack",[]),hotspot=data.get("hotspot",{}),
        thermal_grid_rows=int(data.get("grid_rows",64)),thermal_grid_cols=int(data.get("grid_cols",64)),
        aliases=aliases,warnings=warnings,input_sha256=hashlib.sha256(data_bytes).hexdigest(),
        connectivity_grain="module_pair_signal_counts_not_gate_level_netlist")
