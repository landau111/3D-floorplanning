"""Thermal screening and optional direct HotSpot 3-D grid invocation."""
from __future__ import annotations

import csv
import json
import math
import subprocess
from pathlib import Path


def proxy_temperature(config: dict, rects: dict) -> dict:
    """Two-layer steady conductance network; all constants are assumptions."""
    p = config["thermal_proxy"]
    nx, ny = p["grid_cols"], p["grid_rows"]
    width, height = config["die_width_mm"], config["die_height_mm"]
    dx, dy = width / nx, height / ny
    power = [[[0.0 for _ in range(nx)] for _ in range(ny)] for _ in range(2)]
    for name, (x, y, w, h, layer) in rects.items():
        z = 0 if layer == "bottom" else 1
        density = config["modules"][name]["power_w"] / (w * h)
        for iy in range(ny):
            overlap_y = max(0.0, min(y + h, (iy + 1) * dy) - max(y, iy * dy))
            if not overlap_y:
                continue
            for ix in range(nx):
                overlap_x = max(0.0, min(x + w, (ix + 1) * dx) - max(x, ix * dx))
                power[z][iy][ix] += density * overlap_x * overlap_y
    expected = sum(m["power_w"] for m in config["modules"].values())
    actual = sum(v for layer in power for row in layer for v in row)
    if abs(expected - actual) > 1e-8:
        raise ValueError("Thermal grid did not conserve module power")
    gxy = p["lateral_G_W_K"]
    gz = p["intertier_G_W_K"]
    gs = p["top_sink_G_W_K"]
    temp = [[[0.0 for _ in range(nx)] for _ in range(ny)] for _ in range(2)]
    residual = float("inf")
    for iteration in range(12000):
        residual = 0.0
        for z in (1, 0):
            for iy in range(ny):
                for ix in range(nx):
                    neighbors = []
                    if ix: neighbors.append(temp[z][iy][ix - 1])
                    if ix + 1 < nx: neighbors.append(temp[z][iy][ix + 1])
                    if iy: neighbors.append(temp[z][iy - 1][ix])
                    if iy + 1 < ny: neighbors.append(temp[z][iy + 1][ix])
                    denominator = len(neighbors) * gxy + gz + (gs if z else 0)
                    target = (power[z][iy][ix] + gxy * sum(neighbors) + gz * temp[1-z][iy][ix]) / denominator
                    old = temp[z][iy][ix]
                    temp[z][iy][ix] = old + 1.35 * (target - old)
                    residual = max(residual, abs(temp[z][iy][ix] - old))
        if residual < 1e-7:
            break
    else:
        raise RuntimeError(f"Thermal proxy failed to converge; residual {residual}")
    offset = p["ambient_C"] + p["package_R_K_W"] * expected
    maps = [[[offset + temp[z][iy][ix] for ix in range(nx)] for iy in range(ny)] for z in range(2)]
    return {"backend": "assumed_conductance_proxy", "temperature_C": maps,
            "peak_C": max(v for layer in maps for row in layer for v in row),
            "mean_C": sum(v for layer in maps for row in layer for v in row) / (2 * nx * ny),
            "power_conservation_error_W": abs(expected - actual),
            "iterations": iteration + 1, "residual_C": residual,
            "note": "Assumed conductances and package resistance; not calibrated HotSpot."}


def hotspot_inputs(config: dict, rects: dict, folder: Path) -> dict:
    """Write exact rectangular cover, 3-D LCF and steady power trace in SI units."""
    folder.mkdir(parents=True, exist_ok=True)
    names, watts = [], []
    for layer in ("top", "bottom"):
        placed = [(n, r) for n, r in rects.items() if r[4] == layer]
        xs = sorted(set([0.0, config["die_width_mm"]] + [v for _, r in placed for v in (r[0], r[0] + r[2])]))
        ys = sorted(set([0.0, config["die_height_mm"]] + [v for _, r in placed for v in (r[1], r[1] + r[3])]))
        lines = []
        for ix, (x0, x1) in enumerate(zip(xs, xs[1:])):
            for iy, (y0, y1) in enumerate(zip(ys, ys[1:])):
                if x1 - x0 < 1e-10 or y1 - y0 < 1e-10:
                    continue
                mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                owner = next((n for n, r in placed if r[0] <= mx < r[0] + r[2] and r[1] <= my < r[1] + r[3]), None)
                name = f"{layer}_{owner or 'dead'}_{ix}_{iy}"
                names.append(name)
                watts.append(config["modules"][owner]["power_w"] * (x1 - x0) * (y1 - y0) /
                             (rects[owner][2] * rects[owner][3]) if owner else 0.0)
                lines.append(f"{name} {(x1-x0)*1e-3:.12g} {(y1-y0)*1e-3:.12g} {x0*1e-3:.12g} {y0*1e-3:.12g}")
        (folder / f"{layer}.flp").write_text("\n".join(lines) + "\n", encoding="ascii")
    if abs(sum(watts) - sum(m["power_w"] for m in config["modules"].values())) > 1e-7:
        raise ValueError("HotSpot power trace does not conserve power")
    (folder / "power.ptrace").write_text(" ".join(names) + "\n" + " ".join(f"{w:.12g}" for w in watts) + "\n", encoding="ascii")
    h = config["hotspot"]
    # LCF lists layers from heat-sink side to far side; physical labels differ from layer numbers.
    lcf = (f"1\nY\nY\n{h['volumetric_heat_capacity_J_m3_K']:.8g}\n{h['thermal_resistivity_m_K_W']:.8g}\n{h['silicon_thickness_um']*1e-6:.8g}\ntop.flp\n"
           f"0\nY\nY\n{h['volumetric_heat_capacity_J_m3_K']:.8g}\n{h['thermal_resistivity_m_K_W']:.8g}\n{h['silicon_thickness_um']*1e-6:.8g}\nbottom.flp\n")
    (folder / "stack.lcf").write_text(lcf, encoding="ascii")
    return {"floorplan_elements": len(names), "total_power_W": sum(watts), "directory": folder.name}


def run_hotspot(executable: str, config: dict, rects: dict, folder: Path) -> dict:
    inputs = hotspot_inputs(config, rects, folder)
    p = config["thermal_proxy"]
    command = [executable, "-model_type", "grid", "-grid_layer_file", "stack.lcf",
               "-f", "top.flp", "-p", "power.ptrace", "-steady_file", "hotspot.steady",
               "-grid_steady_file", "hotspot.grid.steady", "-grid_rows", str(p["grid_rows"]),
               "-grid_cols", str(p["grid_cols"]), "-ambient", str(p["ambient_C"] + 273.15)]
    completed = subprocess.run(command, cwd=folder, capture_output=True, text=True, timeout=180)
    (folder / "hotspot.stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (folder / "hotspot.stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"HotSpot exited {completed.returncode}: {completed.stderr[-1200:]}")
    raw = (folder / "hotspot.grid.steady").read_text(encoding="utf-8")
    layers = {}
    active = None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("Layer "):
            active = int(line.split()[1].rstrip(":"))
            layers[active] = []
        elif active is not None and line:
            tokens = line.split()
            if len(tokens) >= 2:
                layers[active].append(float(tokens[1]) - 273.15)
    nx, ny = p["grid_cols"], p["grid_rows"]
    if not {0, 1}.issubset(layers) or any(len(layers[z]) != nx * ny for z in (0, 1)):
        raise ValueError("Unexpected HotSpot grid output; inspect hotspot.grid.steady")
    maps = [[layers[z][i*nx:(i+1)*nx] for i in range(ny)] for z in (0, 1)]
    return {"backend": "HotSpot", "temperature_C": maps,
            "peak_C": max(v for layer in maps for row in layer for v in row),
            "mean_C": sum(v for layer in maps for row in layer for v in row)/(2*nx*ny),
            "inputs": inputs, "command": command}


def temperature_svg(path: Path, config: dict, rects: dict, thermal: dict, limits: tuple[float, float]) -> None:
    from html import escape
    maps = thermal["temperature_C"]
    ny, nx = len(maps[0]), len(maps[0][0])
    scale = 440
    dw, dh = config["die_width_mm"] * scale, config["die_height_mm"] * scale
    lo, hi = limits
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{2*dw+130:.0f}" height="{dh+100:.0f}">',
           '<style>text{font:12px Arial,sans-serif}.title{font-size:16px;font-weight:bold}</style>']
    for z, layer in enumerate(("bottom", "top")):
        left, top = 25 + z * (dw + 75), 42
        out.append(f'<text class="title" x="{left}" y="24">{layer}: peak {max(v for row in maps[z] for v in row):.1f} C</text>')
        for iy in range(ny):
            for ix in range(nx):
                v = maps[z][iy][ix]
                t = min(1, max(0, (v - lo) / max(.001, hi - lo)))
                red = round(35 + 220*t); green = round(88 + 100*(1-t)); blue = round(210 - 185*t)
                x = left + ix*dw/nx
                y = top + (ny-iy-1)*dh/ny
                out.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{dw/nx+.1:.2f}" height="{dh/ny+.1:.2f}" fill="rgb({red},{green},{blue})"/>')
        for name, r in rects.items():
            if r[4] == layer:
                x = left + r[0]*scale; y = top + (config["die_height_mm"]-r[1]-r[3])*scale
                out.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{r[2]*scale:.2f}" height="{r[3]*scale:.2f}" fill="none" stroke="white" stroke-width="1.5"/>')
                out.append(f'<text x="{x+3:.2f}" y="{y+14:.2f}" fill="white" stroke="#14202b" stroke-width=".3" paint-order="stroke">{escape(name)}</text>')
    out.append(f'<text x="25" y="{dh+75:.0f}">{escape(thermal["backend"])} | shared scale: {lo:.1f} to {hi:.1f} C</text>')
    out.append('</svg>')
    path.write_text("\n".join(out), encoding="utf-8")
