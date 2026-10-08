"""HotSpot adapter and plots. No local thermal equation solver."""

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Tuple


def find_hotspot(executable=None):
    candidate = executable or os.environ.get("HOTSPOT_EXE") or shutil.which("hotspot")
    candidate = candidate or str(Path(__file__).resolve().parents[1] / "third_party/HotSpot/hotspot")
    candidate = shutil.which(str(candidate)) or candidate
    path = Path(candidate).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError("HotSpot missing. Run 'make hotspot' on Linux/WSL or use --hotspot-exe PATH.")
    return str(path)


def hotspot_inputs(config: dict, rects: dict, folder: Path) -> dict:
    """Exact rectangular cover in SI units, with zero-power empty silicon.

    Power trace follows increasing layer index. LCF TEXT lists sink side first.
    """
    from optimize import geometry_ok
    if set(rects) != set(config["modules"]) or not geometry_ok(config, rects):
        raise ValueError("HotSpot requires a complete legal geometric placement")
    folder.mkdir(parents=True, exist_ok=True)
    names, watts, owners = [], [], {}
    power_error = 0.0
    for layer in ("bottom", "top"):
        placed = [(n, r) for n, r in rects.items() if r[4] == layer]
        xs = sorted(set([0.0, config["die_width_mm"]] + [v for _, r in placed for v in (r[0], r[0] + r[2])]))
        ys = sorted(set([0.0, config["die_height_mm"]] + [v for _, r in placed for v in (r[1], r[1] + r[3])]))
        lines, module_power = [], {n: 0.0 for n, _ in placed}
        for ix, (x0, x1) in enumerate(zip(xs, xs[1:])):
            for iy, (y0, y1) in enumerate(zip(ys, ys[1:])):
                if x1-x0 < 1e-10 or y1-y0 < 1e-10:
                    continue
                mx, my = (x0+x1)/2, (y0+y1)/2
                owner = next((n for n, r in placed if r[0] <= mx < r[0]+r[2] and r[1] <= my < r[1]+r[3]), None)
                name = "{}_{}_{}_{}".format(layer, owner or 'dead', ix, iy)
                power = (config["modules"][owner]["power_w"] * (x1-x0)*(y1-y0) /
                         (rects[owner][2]*rects[owner][3])) if owner else 0.0
                names.append(name); watts.append(power)
                if owner:
                    module_power[owner] += power
                    owners[name] = owner
                lines.append("{} {:.15g} {:.15g} {:.15g} {:.15g}".format(name, (x1-x0)*1e-3, (y1-y0)*1e-3, x0*1e-3, y0*1e-3))
        for name, power in module_power.items():
            power_error = max(power_error, abs(power-config["modules"][name]["power_w"]))
        (folder / (layer+".flp")).write_text("\n".join(lines)+"\n", encoding="ascii")
    if power_error > 1e-8:
        raise ValueError("HotSpot trace does not conserve each module's power")
    trace = " ".join(names)+"\n"+" ".join("{:.15g}".format(w) for w in watts)+"\n"
    if len(names) > 8192 or max(len(line) for line in trace.splitlines()) >= 65535:
        raise ValueError("Floorplan cover exceeds bundled HotSpot trace limits; reduce partition count")
    (folder / "power.ptrace").write_text(trace, encoding="ascii")
    lcf, mapping = [], {}
    for index, layer in reversed(list(enumerate(config["stack"]))):
        powered = layer["power_layer"] != "none"
        flp = layer["power_layer"]+".flp" if powered else layer["name"]+".flp"
        if powered:
            mapping[layer["power_layer"]] = index
        else:
            (folder / flp).write_text("{} {:.15g} {:.15g} 0 0\n".format(layer["name"], config["die_width_mm"]*1e-3, config["die_height_mm"]*1e-3), encoding="ascii")
        lcf += [str(index), "Y", "Y" if powered else "N", str(layer["heat_capacity_J_m3_K"]),
                "{:.15g}".format(1/layer["conductivity_W_m_K"]),
                "{:.15g}".format(layer["thickness_um"]*1e-6), flp]
    (folder / "stack.lcf").write_text("\n".join(lcf)+"\n", encoding="ascii")
    parameters = dict(config["hotspot"])
    parameters.update(model_type="grid", detailed_3D="on", grid_rows=config["grid_rows"],
                      grid_cols=config["grid_cols"], ambient=config["ambient_c"]+273.15,
                      init_temp=config["ambient_c"]+273.15, model_secondary=0, leakage_used=0,
                      package_model_used=0, grid_map_mode="max", use_microfluidic_cooling=0)
    (folder / "hotspot.config").write_text("\n".join("-{} {}".format(k,v) for k,v in sorted(parameters.items()))+"\n", encoding="ascii")
    info = {"floorplan_elements": len(names), "total_power_W": sum(watts),
            "power_conservation_error_W": power_error, "active_layer_indices": mapping,
            "stack": config["stack"], "package_parameters": config["hotspot"],
            "power_note": "Only provided module powers; no additional leakage model.", "element_owners": owners}
    (folder / "input_manifest.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info


def parse_grid(raw, nx, ny, layer_indices):
    """HotSpot row zero is at TOP; internal row zero is at the bottom."""
    layers, active = {}, None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.fullmatch(r"Layer (\d+):", line)
        if match:
            active = int(match.group(1))
            if active in layers:
                raise ValueError("Repeated HotSpot grid layer")
            layers[active] = {}
        else:
            tokens = line.split()
            if active is None or len(tokens) != 2:
                raise ValueError("Malformed HotSpot grid output")
            index, kelvin = int(tokens[0]), float(tokens[1])
            if index in layers[active] or not 0 <= index < nx*ny or not math.isfinite(kelvin) or kelvin <= 0:
                raise ValueError("Invalid HotSpot cell temperature/index")
            layers[active][index] = kelvin-273.15
    maps = []
    for layer in ("bottom", "top"):
        cells = layers.get(layer_indices[layer], {})
        if len(cells) != nx*ny:
            raise ValueError("Incomplete powered HotSpot grid layer: "+layer)
        maps.append([[cells[(ny-1-row)*nx+col] for col in range(nx)] for row in range(ny)])
    return maps


def module_temperatures(config, rects, maps):
    """Maximum over every grid cell intersecting each module."""
    nx, ny = config["grid_cols"], config["grid_rows"]
    dx, dy = config["die_width_mm"]/nx, config["die_height_mm"]/ny
    result = {}
    for name, (x,y,w,h,layer) in rects.items():
        cells = maps[0 if layer == "bottom" else 1]
        ix0, iy0 = max(0, math.floor(x/dx)), max(0, math.floor(y/dy))
        ix1, iy1 = min(nx, math.ceil((x+w)/dx)), min(ny, math.ceil((y+h)/dy))
        result[name] = max(cells[row][col] for row in range(iy0,iy1) for col in range(ix0,ix1))
    return result


def run_hotspot(executable: str, config: dict, rects: dict, folder: Path) -> dict:
    executable = find_hotspot(executable)
    folder = folder.resolve()
    inputs = hotspot_inputs(config, rects, folder)
    command = [executable, "-c", "hotspot.config", "-grid_layer_file", "stack.lcf",
               "-f", "bottom.flp", "-p", "power.ptrace", "-steady_file", "hotspot.steady",
               "-grid_steady_file", "hotspot.grid.steady"]
    for name in ("hotspot.steady", "hotspot.grid.steady"):
        path = folder / name
        if path.exists():
            path.unlink()
    (folder / "command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")
    try:
        completed = subprocess.run(command, cwd=str(folder), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("Cannot run HotSpot: {}. Use Linux/WSL for bundled binary.".format(error))
    (folder / "hotspot.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (folder / "hotspot.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError("HotSpot exited {}: {}".format(completed.returncode, completed.stderr[-1200:]))
    raw = (folder / "hotspot.grid.steady").read_text(encoding="ascii")
    maps = parse_grid(raw, config["grid_cols"], config["grid_rows"], inputs["active_layer_indices"])
    values = [v for layer in maps for row in layer for v in row]
    if min(values) < config["ambient_c"]-.02:
        raise ValueError("HotSpot returned below-ambient temperature with positive power")
    return {"backend": "HotSpot", "temperature_C": maps, "peak_C": max(values),
            "mean_C": sum(values)/len(values), "module_peak_C": module_temperatures(config,rects,maps),
            "input_directory": str(folder), "command": command,
            "executable_sha256": hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
            "inputs": {k:v for k,v in inputs.items() if k != "element_owners"}}


def temperature_svg(path: Path, config: dict, rects: dict, thermal: dict, limits: Tuple[float,float]) -> None:
    from html import escape
    maps = thermal["temperature_C"]
    ny, nx = len(maps[0]), len(maps[0][0])
    scale = 440
    dw, dh = config["die_width_mm"]*scale, config["die_height_mm"]*scale
    lo, hi = limits
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="{:.0f}" height="{:.0f}">'.format(2*dw+130,dh+100),
           '<style>text{font:12px Arial,sans-serif}.title{font-size:16px;font-weight:bold}</style>']
    for z,layer in enumerate(("bottom","top")):
        left, top = 25+z*(dw+75),42
        out.append('<text class="title" x="{}" y="24">{}: peak {:.3f} C</text>'.format(left,layer,max(v for row in maps[z] for v in row)))
        for iy in range(ny):
            for ix in range(nx):
                t = min(1,max(0,(maps[z][iy][ix]-lo)/max(.001,hi-lo)))
                red,green,blue = round(35+220*t),round(88+100*(1-t)),round(210-185*t)
                x,y = left+ix*dw/nx,top+(ny-iy-1)*dh/ny
                out.append('<rect x="{:.2f}" y="{:.2f}" width="{:.2f}" height="{:.2f}" fill="rgb({},{},{})"/>'.format(x,y,dw/nx+.1,dh/ny+.1,red,green,blue))
        for name,r in rects.items():
            if r[4] == layer:
                x,y = left+r[0]*scale,top+(config["die_height_mm"]-r[1]-r[3])*scale
                out.append('<rect x="{:.2f}" y="{:.2f}" width="{:.2f}" height="{:.2f}" fill="none" stroke="white" stroke-width="1.5"/>'.format(x,y,r[2]*scale,r[3]*scale))
                out.append('<text x="{:.2f}" y="{:.2f}" fill="white" stroke="#14202b" stroke-width=".3" paint-order="stroke">{}</text>'.format(x+3,y+14,escape(name)))
    out.append('<text x="25" y="{:.0f}">HotSpot | shared scale: {:.3f} to {:.3f} C | assumed stack/package</text>'.format(dh+75,lo,hi))
    bar_x,bar_y,bar_w = 620,dh+52,400
    for i in range(64):
        t = i/63
        red,green,blue = round(35+220*t),round(88+100*(1-t)),round(210-185*t)
        out.append('<rect x="{:.2f}" y="{:.2f}" width="{:.2f}" height="12" fill="rgb({},{},{})"/>'.format(bar_x+i*bar_w/64,bar_y,bar_w/64+.1,red,green,blue))
    out.append('<text x="{}" y="{:.0f}">{:.3f} C</text>'.format(bar_x,bar_y+30,lo))
    out.append('<text x="{}" y="{:.0f}">{:.3f} C</text>'.format(bar_x+bar_w-65,bar_y+30,hi))
    out.append('</svg>')
    path.write_text("\n".join(out), encoding="utf-8")
