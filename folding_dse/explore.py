"""Multiobjective exploration, Pareto screening, and thermal map generation."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import random
import shutil
from pathlib import Path

from optimize import anneal, initial_fixed, load_config, metrics, validate, write_svg
from thermal import hotspot_inputs, proxy_temperature, run_hotspot, temperature_svg


PROFILES = {
    "balanced": {"wirelength": 1.0, "cross_layer": .18, "thermal_spread": .18, "anchor": .04, "layer_balance": .02},
    "wire": {"wirelength": 1.7, "cross_layer": .08, "thermal_spread": .08, "anchor": .02, "layer_balance": .01},
    "thermal": {"wirelength": .55, "cross_layer": .10, "thermal_spread": .95, "anchor": .02, "layer_balance": .10},
    "bond": {"wirelength": .70, "cross_layer": .90, "thermal_spread": .12, "anchor": .02, "layer_balance": .02},
    "anchor": {"wirelength": .70, "cross_layer": .12, "thermal_spread": .15, "anchor": .45, "layer_balance": .02},
}


def objectives(candidate):
    m = candidate["metrics"]
    return (m["mean_weighted_manhattan_mm"], m["cross_layer_signals"], candidate["thermal"]["peak_C"])


def pareto_flags(candidates):
    points = [objectives(c) for c in candidates]
    return [not any(j != i and all(v <= u + 1e-9 for v, u in zip(p, point)) and
                    any(v < u - 1e-9 for v, u in zip(p, point))
                    for j, p in enumerate(points)) for i, point in enumerate(points)]


def select_candidates(candidates, flags, count):
    points = [objectives(c) for c in candidates]
    lows = [min(p[k] for p in points) for k in range(3)]
    highs = [max(p[k] for p in points) for k in range(3)]
    normalized = [tuple((p[k] - lows[k]) / max(1e-9, highs[k] - lows[k]) for k in range(3)) for p in points]
    front = [i for i, flag in enumerate(flags) if flag]
    # Include objective extremes, then maximize spread along the front.
    chosen = []
    for k in range(3):
        index = min(front, key=lambda i: normalized[i][k])
        if index not in chosen and len(chosen) < count:
            chosen.append(index)
    while len(chosen) < min(count, len(front)):
        remaining = [i for i in front if i not in chosen]
        diverse_profiles = [i for i in remaining if candidates[i]["profile"] not in {candidates[j]["profile"] for j in chosen}]
        if diverse_profiles:
            remaining = diverse_profiles
        chosen.append(max(remaining, key=lambda i: min(sum((normalized[i][k] - normalized[j][k])**2 for k in range(3)) for j in chosen)))
    # If the strict Pareto front is tiny, retain the closest additional tradeoffs.
    while len(chosen) < min(count, len(candidates)):
        remaining = [i for i in range(len(candidates)) if i not in chosen]
        chosen.append(min(remaining, key=lambda i: sum(normalized[i]) + (0 if flags[i] else .1)))
    return chosen


def pareto_svg(path: Path, candidates, flags, selected):
    points = [objectives(c) for c in candidates]
    panels = [(0, 2, "mean weighted wire length (mm)", "peak temperature (C)"),
              (1, 2, "cross-layer signals", "peak temperature (C)")]
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="480">',
           '<style>text{font:13px Arial,sans-serif}.title{font-size:17px;font-weight:bold}</style>',
           f'<text class="title" x="25" y="25">Pareto screening: {candidates[0]["thermal"]["backend"]}</text>']
    colors = ("#d62828", "#0a9396", "#6a4c93", "#f77f00", "#3a86ff")
    for panel, (xi, yi, xlabel, ylabel) in enumerate(panels):
        left, top, width, height = 65 + panel * 530, 65, 410, 320
        xmin, xmax = min(p[xi] for p in points), max(p[xi] for p in points)
        ymin, ymax = min(p[yi] for p in points), max(p[yi] for p in points)
        xmax = xmax if xmax > xmin else xmin + 1
        ymax = ymax if ymax > ymin else ymin + 1
        out.append(f'<rect x="{left}" y="{top}" width="{width}" height="{height}" fill="#f7fafc" stroke="#333"/>')
        for i, point in enumerate(points):
            x = left + (point[xi]-xmin)/(xmax-xmin)*width
            y = top + height - (point[yi]-ymin)/(ymax-ymin)*height
            color = colors[selected.index(i)] if i in selected else ("#2364aa" if flags[i] else "#b8c4cc")
            radius = 7 if i in selected else (4 if flags[i] else 3)
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius}" fill="{color}" stroke="white"><title>{candidates[i]["profile"]}: {point}</title></circle>')
        out.append(f'<text x="{left}" y="{top+height+25}">{xlabel}: {xmin:.3g} to {xmax:.3g}</text>')
        out.append(f'<text x="{left}" y="{top+height+45}">{ylabel}: {ymin:.1f} to {ymax:.1f}</text>')
    out.append('<text x="30" y="460" fill="#2364aa">Blue: nondominated; gray: dominated; colors: selected layouts</text>')
    out.append('</svg>')
    path.write_text("\n".join(out), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "pareto_results")
    parser.add_argument("--hotspot-exe", help="Path to built HotSpot executable; auto-detects PATH if omitted")
    parser.add_argument("--steps", type=int, default=4500)
    parser.add_argument("--restarts", type=int, default=2)
    parser.add_argument("--selected", type=int, default=4)
    args = parser.parse_args()
    config = load_config(args.config)
    validate(config)
    args.output.mkdir(parents=True, exist_ok=True)
    total = sum(m.get("area_mm2", m.get("rect", [0,0,0,0])[2] * m.get("rect", [0,0,0,0])[3]) for m in config["modules"].values())
    cap = 2*config["die_area_limit_mm2"]*config["area_margin"]
    applied = config.get("applied_area_multiplier", 1.0)
    requested = config.get("requested_area_multiplier", applied)
    feasibility = {"requested_multiplier": requested, "applied_multiplier": applied,
                   "requested_total_area_mm2": total/applied*requested,
                   "applied_total_area_mm2": total, "two_layer_area_capacity_mm2": cap,
                   "requested_area_feasible": total/applied*requested <= cap,
                   "note": "Area is only a necessary condition; rectangle packing and spacing are checked during search."}
    (args.output / "area_feasibility.json").write_text(json.dumps(feasibility, indent=2), encoding="utf-8")
    pool = []
    for profile_index, (profile, weights) in enumerate(PROFILES.items()):
        c = copy.deepcopy(config)
        c["objective_weights"] = weights
        snapshots = []
        result = None
        for attempt in range(5):
            try:
                result = anneal(c, c["search"]["seed"] + profile_index*100003 + attempt*7919,
                                args.restarts, args.steps, snapshots)
                break
            except RuntimeError:
                snapshots.clear()
        if result is None:
            print(f"{profile}: no legal initial packing in 5 seed groups")
            continue
        best, best_m, history = result
        # Keep per-restart improvements and the profile winner; identical states are removed later.
        snapshots.append((best, best_m))
        for rects, _ in snapshots:
            if not metrics(config, rects)["feasible"]:
                continue
            fingerprint = tuple((n, round(r[0], 5), round(r[1], 5), round(r[2], 5), r[4]) for n, r in sorted(rects.items()))
            if any(item["fingerprint"] == fingerprint for item in pool):
                continue
            pool.append({"profile": profile, "rects": rects, "fingerprint": fingerprint,
                         "metrics": metrics(config, rects), "thermal": proxy_temperature(config, rects)})
        print(f"{profile}: best profile score {best_m['score']:.4f}, accepted {[h['accepted_moves'] for h in history]}", flush=True)
    if not pool:
        raise RuntimeError("No proxy-feasible candidate; review area, geometry, and bond density")
    executable = args.hotspot_exe or shutil.which("hotspot") or shutil.which("hotspot.exe")
    if executable:
        # Re-evaluate the entire candidate pool so Pareto dominance uses HotSpot temperatures.
        for i, item in enumerate(pool):
            item["thermal"] = run_hotspot(executable, config, item["rects"], args.output / "hotspot_pool" / f"candidate_{i+1:02d}")
    flags = pareto_flags(pool)
    selected = select_candidates(pool, flags, args.selected)
    # Generate all HotSpot inputs even when no binary is available, so a later run is direct.
    thermal_results = {}
    for rank, i in enumerate(selected, 1):
        item = pool[i]
        folder = args.output / f"layout_{rank:02d}"
        folder.mkdir(exist_ok=True)
        write_svg(folder / "layout.svg", config, item["rects"])
        inputs = hotspot_inputs(config, item["rects"], folder / "hotspot_inputs")
        thermal = item["thermal"]
        thermal_results[i] = thermal
        (folder / "layout.json").write_text(json.dumps({"profile": item["profile"], "pareto": flags[i],
                        "metrics": item["metrics"], "thermal": {k:v for k,v in thermal.items() if k != "temperature_C"},
                        "modules": {n: {"x_mm": r[0], "y_mm": r[1], "w_mm": r[2], "h_mm": r[3], "layer": r[4]} for n,r in item["rects"].items()},
                        "hotspot_inputs": inputs}, indent=2, ensure_ascii=False), encoding="utf-8")
        with (folder / "temperature.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["layer", "row_from_bottom", "column_from_left", "temperature_C", "backend"])
            for z, layer in enumerate(thermal["temperature_C"]):
                for row, values in enumerate(layer):
                    for col, temp in enumerate(values):
                        writer.writerow([( "bottom", "top")[z], row, col, round(temp, 6), thermal["backend"]])
    lo = min(v for result in thermal_results.values() for layer in result["temperature_C"] for row in layer for v in row)
    hi = max(v for result in thermal_results.values() for layer in result["temperature_C"] for row in layer for v in row)
    for rank, i in enumerate(selected, 1):
        folder = args.output / f"layout_{rank:02d}"
        temperature_svg(folder / "temperature.svg", config, pool[i]["rects"], thermal_results[i], (lo, hi))
    with (args.output / "pareto_candidates.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate", "profile", "pareto", "selected_rank", "wire_mm", "cross_layer_signals",
                         "peak_temperature_C", "peak_bond_density_mm2", "area_bottom_mm2", "area_top_mm2", "anchor_displacement"])
        for i, item in enumerate(pool):
            m = item["metrics"]
            writer.writerow([i+1, item["profile"], flags[i], selected.index(i)+1 if i in selected else "",
                             m["mean_weighted_manhattan_mm"], m["cross_layer_signals"], item["thermal"]["peak_C"],
                             m["estimated_peak_bond_density_per_mm2"], m["layer_area_mm2"]["bottom"],
                             m["layer_area_mm2"]["top"], m["anchor_displacement_normalized"]])
    pareto_svg(args.output / "pareto.svg", pool, flags, selected)
    manifest = {"config": args.config.name, "candidate_count": len(pool),
                "pareto_count": sum(flags), "selected": [{"layout": f"layout_{rank:02d}", "profile": pool[i]["profile"],
                    "pareto": flags[i], "wire_mm": objectives(pool[i])[0], "cross_layer_signals": objectives(pool[i])[1],
                    "pareto_peak_temperature_C": objectives(pool[i])[2], "temperature_backend": thermal_results[i]["backend"],
                    "peak_temperature_C": thermal_results[i]["peak_C"]} for rank,i in enumerate(selected,1)],
                "thermal_warning": "Proxy temperatures use uncalibrated conductances; HotSpot temperatures also require calibrated package/material/power input.",
                "area_feasibility": feasibility}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"candidates": len(pool), "pareto": sum(flags), "selected": len(selected),
                      "thermal_backend": "HotSpot" if executable else "assumed_conductance_proxy",
                      "output": str(args.output.resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
