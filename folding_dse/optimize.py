"""Config-driven, module-granularity two-die folding exploration (proxy model)."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import random
import re
from pathlib import Path


SHAPES = (0.55, 0.75, 1.0, 1.33, 1.8)  # width / height; area remains exact
LAYERS = ("bottom", "top")


def _scalar(value: str):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        contents = value[1:-1].strip()
        return [_scalar(part) for part in contents.split(",")] if contents else []
    if re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value):
        return float(value)
    if value in ("true", "false"):
        return value == "true"
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", value):
        raise ValueError(f"Unsupported YAML scalar in compact configuration: {value!r}")
    return value


def _parse_compact_yaml(raw: str) -> dict:
    """Read the user's original flat-key/list YAML style without third-party modules."""
    data = {}
    current = None
    for number, source in enumerate(raw.splitlines(), 1):
        line = source.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            if current is None or not isinstance(data[current], list):
                raise ValueError(f"Line {number}: list item has no list key")
            item = stripped[2:].strip()
            if ": " in item and not item.startswith("["):
                key, value = item.split(": ", 1)
                data[current].append({key: _scalar(value)})
            else:
                data[current].append(_scalar(item))
            continue
        if line[0].isspace():
            if current != "power_w" or not isinstance(data[current], dict) or ": " not in stripped:
                raise ValueError(f"Line {number}: unsupported nested entry")
            key, value = stripped.split(": ", 1)
            data[current][key] = _scalar(value)
            continue
        if ":" not in line:
            raise ValueError(f"Line {number}: expected 'key: value' or a comment")
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or key in data:
            raise ValueError(f"Line {number}: invalid or duplicate key {key!r}")
        if value:
            data[key] = _scalar(value)
            current = None
        else:
            data[key] = {} if key == "power_w" else []
            current = key
    return data


def _normalize_compact_config(raw: dict) -> dict:
    if "modules" in raw:
        return raw
    base = json.loads((Path(__file__).parent / "config.yaml").read_text(encoding="utf-8"))
    result = copy.deepcopy(base)
    result["provenance"] = "Synthetic assumptions from the compact user-style YAML input; solver defaults from config.yaml."
    fixed = list(raw["fixed_bottom"]) + list(raw["fixed_top"])
    movable = list(raw["movable_modules"])
    names = fixed + movable
    if len(names) != len(set(names)) or set(raw["power_w"]) != set(names):
        raise ValueError("Module lists and power_w must name the same modules exactly once")
    result["modules"] = {}
    for name in names:
        geometry = raw.get(name)
        if not isinstance(geometry, list) or len(geometry) != (4 if name in fixed else 3):
            raise ValueError(f"Invalid geometry list for {name}")
        result["modules"][name] = ({"kind": "hard", "rect": geometry, "power_w": raw["power_w"][name]}
                                    if name in fixed else
                                    {"kind": "soft", "anchor": geometry[:2], "area_mm2": geometry[2],
                                     "power_w": raw["power_w"][name]})
    result["fixed_bottom"] = list(raw["fixed_bottom"])
    result["fixed_top"] = list(raw["fixed_top"])
    result["movable_initial_layer"] = {}
    for pair in raw["movable_initial_layer"]:
        if not isinstance(pair, dict) or len(pair) != 1:
            raise ValueError("movable_initial_layer entries must be '- module: layer'")
        name, layer = next(iter(pair.items()))
        if name in result["movable_initial_layer"]:
            raise ValueError(f"Duplicate initial layer: {name}")
        result["movable_initial_layer"][name] = layer
    result["interconnect"] = raw["interconnect"]
    for key in ("die_width_mm", "die_height_mm", "die_area_limit_mm2", "area_margin",
                "bond_pitch_um", "bond_window_mm", "bond_reserve_fraction", "module_gap_mm",
                "max_density_per_mm2"):
        if key in raw:
            result[key] = raw[key]
    return result


def load_config(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(raw)  # JSON is also YAML 1.2; no dependency for bundled runtime.
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError:
            parsed = _parse_compact_yaml(raw)
        else:
            parsed = yaml.safe_load(raw)
    return _normalize_compact_config(parsed)


def validate(c: dict) -> None:
    if c.get("schema") != "folding-dse-v1":
        raise ValueError("schema must be folding-dse-v1")
    names = set(c["modules"])
    fixed = set(c["fixed_bottom"]) | set(c["fixed_top"])
    if set(c["fixed_bottom"]) & set(c["fixed_top"]):
        raise ValueError("A fixed module cannot be in both layers")
    if fixed != {n for n, m in c["modules"].items() if m["kind"] == "hard"}:
        raise ValueError("fixed lists must contain exactly the hard modules")
    if set(c["movable_initial_layer"]) != names - fixed:
        raise ValueError("movable_initial_layer must list every soft module exactly once")
    if c["die_area_limit_mm2"] > c["die_width_mm"] * c["die_height_mm"]:
        raise ValueError("die_area_limit_mm2 exceeds die geometry")
    if not 0 < c["area_margin"] <= 1 or not 0 <= c["bond_reserve_fraction"] < 1:
        raise ValueError("Invalid margin or bond reserve")
    for n, m in c["modules"].items():
        if m["power_w"] < 0:
            raise ValueError(f"Negative power: {n}")
        if m["kind"] == "hard":
            if len(m["rect"]) != 4 or m["rect"][2] <= 0 or m["rect"][3] <= 0:
                raise ValueError(f"Invalid hard rectangle: {n}")
        elif m["kind"] == "soft":
            if m["area_mm2"] <= 0 or len(m["anchor"]) != 2:
                raise ValueError(f"Invalid soft module: {n}")
            if c["movable_initial_layer"][n] not in LAYERS:
                raise ValueError(f"Invalid initial layer: {n}")
        else:
            raise ValueError(f"Invalid kind: {n}")
    for a, b, count in c["interconnect"]:
        if a not in names or b not in names or a == b or not isinstance(count, int) or count <= 0:
            raise ValueError(f"Invalid interconnect: {a}, {b}, {count}")
    for layer, listed in (("bottom", c["fixed_bottom"]), ("top", c["fixed_top"])):
        rectangles = {n: (*c["modules"][n]["rect"], layer) for n in listed}
        if not geometry_ok(c, rectangles):
            raise ValueError(f"Fixed rectangles invalid or overlapping on {layer}")
    if sum(m.get("area_mm2", m.get("rect", [0, 0, 0, 0])[2] * m.get("rect", [0, 0, 0, 0])[3]) for m in c["modules"].values()) > 2 * c["die_area_limit_mm2"] * c["area_margin"]:
        raise ValueError("Total module area exceeds two-die capacity")


def initial_fixed(c: dict) -> dict:
    return {n: (*m["rect"], "bottom" if n in c["fixed_bottom"] else "top")
            for n, m in c["modules"].items() if m["kind"] == "hard"}


def overlap(a, b, gap: float) -> bool:
    return (a[0] < b[0] + b[2] + gap and b[0] < a[0] + a[2] + gap and
            a[1] < b[1] + b[3] + gap and b[1] < a[1] + a[3] + gap)


def geometry_ok(c: dict, rects: dict) -> bool:
    width, height, gap = c["die_width_mm"], c["die_height_mm"], c["module_gap_mm"]
    cap = c["die_area_limit_mm2"] * c["area_margin"]
    areas = {z: 0.0 for z in LAYERS}
    for n, r in rects.items():
        x, y, w, h, z = r
        if z not in LAYERS or min(x, y) < -1e-9 or w <= 0 or h <= 0 or x + w > width + 1e-9 or y + h > height + 1e-9:
            return False
        areas[z] += w * h
        for other, q in rects.items():
            if n < other and z == q[4] and overlap(r, q, gap):
                return False
    return all(a <= cap + 1e-9 for a in areas.values())


def center(r):
    return r[0] + r[2] / 2, r[1] + r[3] / 2


def bond_bins(c: dict, rects: dict) -> tuple[float, int, float]:
    """Spread each cross-tier bundle over its endpoint bounding box, expanded 50 um.

    This is only a capacity proxy; no individual bond sites are legalized.
    """
    step = c["bond_window_mm"]
    nx = math.ceil(c["die_width_mm"] / step)
    ny = math.ceil(c["die_height_mm"] / step)
    bins = [[0.0] * nx for _ in range(ny)]
    total = 0
    for a, b, n in c["interconnect"]:
        if rects[a][4] == rects[b][4]:
            continue
        total += n
        ra, rb = rects[a], rects[b]
        x0 = max(0.0, min(ra[0], rb[0]) - step / 2)
        y0 = max(0.0, min(ra[1], rb[1]) - step / 2)
        x1 = min(c["die_width_mm"], max(ra[0] + ra[2], rb[0] + rb[2]) + step / 2)
        y1 = min(c["die_height_mm"], max(ra[1] + ra[3], rb[1] + rb[3]) + step / 2)
        area = (x1 - x0) * (y1 - y0)
        for iy in range(ny):
            by0, by1 = iy * step, min((iy + 1) * step, c["die_height_mm"])
            oy = max(0.0, min(y1, by1) - max(y0, by0))
            if not oy:
                continue
            for ix in range(nx):
                bx0, bx1 = ix * step, min((ix + 1) * step, c["die_width_mm"])
                ox = max(0.0, min(x1, bx1) - max(x0, bx0))
                bins[iy][ix] += n * ox * oy / area
    limit_density = min(c["max_density_per_mm2"], (1000 / c["bond_pitch_um"]) ** 2)
    limit_density *= 1 - c["bond_reserve_fraction"]
    peak = max(bins[iy][ix] / ((min((ix + 1) * step, c["die_width_mm"]) - ix * step) *
                               (min((iy + 1) * step, c["die_height_mm"]) - iy * step))
               for iy in range(ny) for ix in range(nx))
    return peak, total, limit_density


def metrics(c: dict, rects: dict) -> dict:
    total_n = sum(link[2] for link in c["interconnect"])
    weighted_wire = 0.0
    cross = 0
    for a, b, n in c["interconnect"]:
        ax, ay = center(rects[a]); bx, by = center(rects[b])
        weighted_wire += n * (abs(ax - bx) + abs(ay - by))
        if rects[a][4] != rects[b][4]:
            cross += n
    area = {z: sum(r[2] * r[3] for r in rects.values() if r[4] == z) for z in LAYERS}
    power = {z: sum(c["modules"][n]["power_w"] for n, r in rects.items() if r[4] == z) for z in LAYERS}
    # Hotspot proxy: Gaussian power smoothing on each layer and weaker cross-layer coupling.
    heat = []
    for z in LAYERS:
        for iy in range(7):
            y = (iy + .5) * c["die_height_mm"] / 7
            for ix in range(8):
                x = (ix + .5) * c["die_width_mm"] / 8
                value = 0.0
                for n, r in rects.items():
                    mx, my = center(r)
                    sigma = .13 + .2 * math.sqrt(r[2] * r[3])
                    value += c["modules"][n]["power_w"] * (1 if r[4] == z else .25) * math.exp(-((x - mx) ** 2 + (y - my) ** 2) / (2 * sigma ** 2))
                heat.append(value)
    anchor = sum(math.dist(center(rects[n]), m["anchor"]) / math.hypot(c["die_width_mm"], c["die_height_mm"])
                 for n, m in c["modules"].items() if m["kind"] == "soft") / len(c["movable_initial_layer"])
    peak_density, bonds, density_limit = bond_bins(c, rects)
    density_over = max(0.0, peak_density / density_limit - 1)
    global_bond_capacity = density_limit * c["die_width_mm"] * c["die_height_mm"]
    global_over = max(0.0, bonds / global_bond_capacity - 1)
    w = c["objective_weights"]
    score = (w["wirelength"] * weighted_wire / total_n / (c["die_width_mm"] + c["die_height_mm"])
             + w["cross_layer"] * cross / total_n
             + w["thermal_spread"] * max(heat) / max(.001, sum(power.values()))
             + w["anchor"] * anchor
             + w["layer_balance"] * abs(power["bottom"] - power["top"]) / max(.001, sum(power.values()))
             + 20 * density_over ** 2 + 20 * global_over ** 2)
    return {"score": score, "weighted_wirelength_mm_signals": weighted_wire,
            "mean_weighted_manhattan_mm": weighted_wire / total_n,
            "cross_layer_signals": cross, "estimated_peak_bond_density_per_mm2": peak_density,
            "bond_density_limit_per_mm2": density_limit, "total_bond_capacity": global_bond_capacity,
            "estimated_thermal_hotspot_index": max(heat), "layer_area_mm2": area,
            "layer_power_w": power, "anchor_displacement_normalized": anchor,
            "feasible": geometry_ok(c, rects) and density_over < 1e-9 and global_over < 1e-9}


def random_rect(c, name: str, layer: str, rng: random.Random, near: bool = False):
    m = c["modules"][name]
    aspect = rng.choice(SHAPES)
    w = math.sqrt(m["area_mm2"] * aspect)
    h = m["area_mm2"] / w
    if near:
        x = m["anchor"][0] - w / 2 + rng.gauss(0, .17)
        y = m["anchor"][1] - h / 2 + rng.gauss(0, .17)
    else:
        x = rng.uniform(0, c["die_width_mm"] - w)
        y = rng.uniform(0, c["die_height_mm"] - h)
    x = min(max(0, x), c["die_width_mm"] - w)
    y = min(max(0, y), c["die_height_mm"] - h)
    return (x, y, w, h, layer)


def construct(c: dict, rng: random.Random) -> dict:
    soft = list(c["movable_initial_layer"])
    # Large modules first reduces late-stage packing failures.
    soft.sort(key=lambda n: -c["modules"][n]["area_mm2"] + rng.uniform(-.004, .004))
    for attempt in range(30):
        rects = initial_fixed(c)
        for name in soft:
            preferred = c["movable_initial_layer"][name]
            found = None
            best = float("inf")
            for _ in range(700):
                layer = preferred if rng.random() < .92 else LAYERS[1 - LAYERS.index(preferred)]
                candidate = random_rect(c, name, layer, rng, near=True)
                trial = {**rects, name: candidate}
                if not geometry_ok(c, trial):
                    continue
                cx, cy = center(candidate)
                ax, ay = c["modules"][name]["anchor"]
                cost = math.hypot(cx - ax, cy - ay) + (.13 if layer != preferred else 0)
                cost += rng.random() * .03
                if cost < best:
                    best, found = cost, candidate
            if found is None:
                break
            rects[name] = found
        if len(rects) == len(c["modules"]):
            return rects
        rng.shuffle(soft)
    raise RuntimeError("Could not pack modules. Check area, fixed macro position, and gap.")


def mutate(c: dict, current: dict, rng: random.Random) -> dict | None:
    name = rng.choice(list(c["movable_initial_layer"]))
    old = current[name]
    mode = rng.random()
    if mode < .18:
        other = rng.choice([n for n in c["movable_initial_layer"] if n != name])
        second = current[other]
        # Center/layer swap lets a packed design cross barriers that single moves cannot.
        ax, ay = center(second); bx, by = center(old)
        first_new = (ax-old[2]/2, ay-old[3]/2, old[2], old[3], second[4])
        second_new = (bx-second[2]/2, by-second[3]/2, second[2], second[3], old[4])
        trial = {**current, name: first_new, other: second_new}
        return trial if geometry_ok(c, trial) else None
    layer = LAYERS[1 - LAYERS.index(old[4])] if mode < .25 else old[4]
    if mode < .45:
        candidate = random_rect(c, name, layer, rng, near=mode < .25)
    else:
        x, y, w, h, _ = old
        if mode < .68:
            aspect = rng.choice(SHAPES)
            w = math.sqrt(c["modules"][name]["area_mm2"] * aspect)
            h = c["modules"][name]["area_mm2"] / w
        x = min(max(0, x + rng.gauss(0, .065)), c["die_width_mm"] - w)
        y = min(max(0, y + rng.gauss(0, .065)), c["die_height_mm"] - h)
        candidate = (x, y, w, h, layer)
    trial = {**current, name: candidate}
    return trial if geometry_ok(c, trial) else None


def anneal(c: dict, seed: int, restarts: int, steps: int, candidates: list | None = None):
    best, best_m = None, None
    history = []
    for restart in range(restarts):
        rng = random.Random(seed + restart * 9973)
        current = construct(c, rng)
        current_m = metrics(c, current)
        restart_best = (current_m["score"], current.copy(), current_m.copy()) if current_m["feasible"] else None
        accepted = 0
        for step in range(steps):
            trial = mutate(c, current, rng)
            if trial is None:
                continue
            trial_m = metrics(c, trial)
            fraction = step / max(1, steps - 1)
            temperature = .035 * (.0008 / .035) ** fraction
            delta = trial_m["score"] - current_m["score"]
            if delta < 0 or rng.random() < math.exp(-delta / temperature):
                current, current_m = trial, trial_m
                accepted += 1
            if current_m["feasible"] and (best_m is None or current_m["score"] < best_m["score"]):
                best, best_m = current.copy(), current_m.copy()
            if current_m["feasible"] and (restart_best is None or current_m["score"] < restart_best[0]):
                restart_best = (current_m["score"], current.copy(), current_m.copy())
            if candidates is not None and step % max(1, steps // 5) == 0 and restart_best is not None:
                candidates.append((restart_best[1].copy(), restart_best[2].copy()))
        history.append({"restart": restart + 1, "final_score": round(current_m["score"], 6),
                        "final_feasible": current_m["feasible"], "accepted_moves": accepted})
        if candidates is not None and restart_best is not None:
            candidates.append((restart_best[1].copy(), restart_best[2].copy()))
    if best is None:
        raise RuntimeError("No density-feasible placement found; inspect density and connectivity assumptions.")
    return best, best_m, history


def write_svg(path: Path, c: dict, rects: dict) -> None:
    from html import escape
    scale, ox, oy = 470, 30, 45
    dw, dh = c["die_width_mm"] * scale, c["die_height_mm"] * scale
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{2 * (dw + 75) + 30:.0f}" height="{dh + 105:.0f}" viewBox="0 0 {2 * (dw + 75) + 30:.0f} {dh + 105:.0f}">',
             '<style>text{font:12px Arial,sans-serif}.title{font-weight:bold;font-size:17px}.hard{fill:#64748b}.soft{fill:#4f9cbb;stroke:#17435a;stroke-width:1}</style>']
    for i, layer in enumerate(LAYERS):
        left = ox + i * (dw + 75)
        lines.append(f'<text class="title" x="{left}" y="25">{layer}</text>')
        lines.append(f'<rect x="{left}" y="{oy}" width="{dw}" height="{dh}" fill="#f7fafc" stroke="#222"/>')
        for n, r in rects.items():
            x, y, w, h, z = r
            if z != layer:
                continue
            px, py = left + x * scale, oy + (c["die_height_mm"] - y - h) * scale
            lines.append(f'<rect class="{"hard" if c["modules"][n]["kind"] == "hard" else "soft"}" x="{px:.2f}" y="{py:.2f}" width="{w * scale:.2f}" height="{h * scale:.2f}"/>')
            lines.append(f'<text x="{px + 3:.2f}" y="{py + 16:.2f}" fill="{"white" if c["modules"][n]["kind"] == "hard" else "#082b3a"}">{escape(n)}</text>')
    lines.append('</svg>')
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="YAML or JSON config")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results")
    parser.add_argument("--steps", type=int, help="Override steps per restart")
    parser.add_argument("--restarts", type=int, help="Override restart count")
    args = parser.parse_args()
    c = load_config(args.config)
    validate(c)
    args.output.mkdir(parents=True, exist_ok=True)
    settings = c["search"]
    baseline = construct(c, random.Random(settings["seed"]))
    baseline_metrics = metrics(c, baseline)
    rects, result, history = anneal(c, settings["seed"], args.restarts or settings["restarts"], args.steps or settings["steps_per_restart"])
    payload = {"config": args.config.name, "seed": settings["seed"],
               "baseline": {"description": "Anchor-biased packing before annealing", "metrics": baseline_metrics},
               "metrics": result,
               "modules": {n: {"x_mm": r[0], "y_mm": r[1], "w_mm": r[2], "h_mm": r[3], "layer": r[4]} for n, r in rects.items()},
               "search_history": history,
               "model_limits": "Proxy only: modules are rectangles; signal bundles are spread uniformly over enlarged endpoint hulls; thermal index is Gaussian power smoothing; no pins, timing graph, detailed routing, bond legalization, or calibrated thermal model."}
    (args.output / "best_layout.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    with (args.output / "best_layout.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["module", "layer", "x_mm", "y_mm", "w_mm", "h_mm", "power_w"])
        for n, r in rects.items():
            writer.writerow([n, r[4], *(round(v, 6) for v in r[:4]), c["modules"][n]["power_w"]])
    write_svg(args.output / "best_layout.svg", c, rects)
    print(json.dumps({"score": round(result["score"], 5), "baseline_score": round(baseline_metrics["score"], 5), "feasible": result["feasible"],
                      "cross_layer_signals": result["cross_layer_signals"],
                      "mean_weighted_manhattan_mm": round(result["mean_weighted_manhattan_mm"], 4),
                      "layer_area_mm2": result["layer_area_mm2"], "output": str(args.output.resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
