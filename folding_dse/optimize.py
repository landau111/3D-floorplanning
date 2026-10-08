"""Module geometry, soft constraints and timing-cost search for folding DSE."""

import copy
import json
import math
import random
import re
from pathlib import Path
from typing import Optional, Tuple


SHAPES = (0.55, 0.75, 1.0, 1.33, 1.8)  # width / height; area remains exact
LAYERS = ("bottom", "top")


def _scalar(value: str):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        contents = value[1:-1].strip()
        return [_scalar(part) for part in _flow_parts(contents)] if contents else []
    if value.startswith("{") and value.endswith("}"):
        result = {}
        for part in _flow_parts(value[1:-1]):
            key, val = part.split(":", 1)
            key = key.strip().strip("\"'")
            if key in result:
                raise ValueError("Duplicate YAML key: " + key)
            result[key] = _scalar(val)
        return result
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return json.loads(value) if value[0] == '"' else value[1:-1].replace("''", "'")
    if re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value):
        return float(value)
    if value in ("true", "false"):
        return value == "true"
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", value):
        raise ValueError(f"Unsupported YAML scalar in compact configuration: {value!r}")
    return value


def _flow_parts(value):
    parts, depth, quote, start = [], 0, None, 0
    for i, char in enumerate(value):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(value[start:i]); start = i + 1
    if value[start:].strip():
        parts.append(value[start:])
    return parts


def _parse_compact_yaml(raw: str) -> dict:
    """Strict subset: mappings, indentless lists, list mappings and flow values.

    This is intentionally not a general YAML implementation (no anchors/tags).
    Duplicate keys are errors so a constraint cannot silently disappear.
    """
    lines = []
    for number, source in enumerate(raw.splitlines(), 1):
        if "\t" in source:
            raise ValueError("Line {}: YAML indentation must use spaces".format(number))
        line = source.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        lines.append((len(line) - len(line.lstrip()), line.strip(), number))

    def entry(text, number):
        if ":" not in text:
            raise ValueError("Line {}: expected key: value".format(number))
        key, val = text.split(":", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError("Line {}: invalid key {}".format(number, key))
        return key, val.strip()

    def block(index, indent, is_list=False):
        result = [] if is_list else {}
        while index < len(lines) and lines[index][0] == indent:
            _, content, number = lines[index]
            if content.startswith("- ") != is_list:
                break
            index += 1
            if is_list:
                content = content[2:]
                if ":" not in content or content[0] in "[{\"'":
                    result.append(_scalar(content)); continue
                key, val = entry(content, number)
                if not val:
                    raise ValueError("Line {}: empty list mapping value".format(number))
                item = {key: _scalar(val)}
                if index < len(lines) and lines[index][0] > indent:
                    if lines[index][0] != indent + 2:
                        raise ValueError("Line {}: list fields require {} spaces".format(lines[index][2], indent + 2))
                    more, index = block(index, indent + 2)
                    if set(more) & set(item):
                        raise ValueError("Duplicate list mapping field")
                    item.update(more)
                result.append(item)
            else:
                key, val = entry(content, number)
                if key in result:
                    raise ValueError("Line {}: duplicate key {}".format(number, key))
                if val:
                    result[key] = _scalar(val)
                elif index < len(lines) and (lines[index][0] > indent or
                        (lines[index][0] == indent and lines[index][1].startswith("- "))):
                    result[key], index = block(index, lines[index][0], lines[index][1].startswith("- "))
                else:
                    result[key] = []
        return result, index

    if not lines:
        raise ValueError("Empty configuration")
    data, end = block(0, 0)
    if end != len(lines):
        raise ValueError("Line {}: unexpected indentation".format(lines[end][2]))
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
                "max_density_per_mm2", "ambient_c", "grid_rows", "grid_cols", "layout_constrains",
                "critical_modules", "net_weights", "rc_temp_alpha", "rc_ref_temp", "hbt_vert_um",
                "stack", "anneal", "timing", "objective_weights", "hotspot", "search", "shape_aspects"):
        if key in raw:
            if isinstance(raw[key], dict) and isinstance(result.get(key), dict):
                result[key].update(raw[key])
            else:
                result[key] = raw[key]
    if "hbt" in raw:
        result["bond_pitch_um"] = raw["hbt"]["pitch_um"]
        result["max_density_per_mm2"] = raw["hbt"]["max_density_per_mm2"]
        if "max_density_per_mm2" in raw and raw["max_density_per_mm2"] != result["max_density_per_mm2"]:
            raise ValueError("Conflicting HBT density limits")
    allowed = set(result) | set(names) | {"hbt", "movable_modules", "power_w"}
    if set(raw) - allowed:
        raise ValueError("Unknown configuration fields: " + str(sorted(set(raw) - allowed)))
    return result


def load_config(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(raw)  # JSON is also YAML 1.2; no dependency for bundled runtime.
    except json.JSONDecodeError:
        parsed = _parse_compact_yaml(raw)
    return _normalize_compact_config(parsed)


def validate(c: dict) -> None:
    if c.get("schema") != "folding-dse-v1":
        raise ValueError("schema must be folding-dse-v1")
    names = set(c["modules"])
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n) for n in names):
        raise ValueError("Module names must be ASCII identifiers for HotSpot")
    if any(not math.isfinite(a) or a <= 0 for a in c.get("shape_aspects", SHAPES)) or not c.get("shape_aspects", SHAPES):
        raise ValueError("shape_aspects must contain positive ratios")
    if set(c["objective_weights"]) != {"wirelength","cross_layer","timing","constraints","temperature","anchor","layer_balance"} or any(not math.isfinite(v) or v < 0 for v in c["objective_weights"].values()):
        raise ValueError("Invalid objective_weights")
    positive = ("die_width_mm", "die_height_mm", "die_area_limit_mm2", "bond_pitch_um",
                "bond_window_mm", "max_density_per_mm2")
    if any(not math.isfinite(c[k]) or c[k] <= 0 for k in positive) or c["module_gap_mm"] < 0:
        raise ValueError("Invalid geometry or HBT parameters")
    if not c["interconnect"]:
        raise ValueError("At least one interconnect is required")
    if not set(c["critical_modules"]) <= names:
        raise ValueError("Unknown critical module")
    if any(not math.isfinite(v) or v <= 0 for v in c["net_weights"].values()) or set(c["net_weights"]) != {"crit_crit", "crit_other", "other_other"}:
        raise ValueError("Invalid net_weights")
    if any(c["timing"][k] <= 0 for k in ("hbt_latency_ps", "clock_period_ps")) or c["hbt_vert_um"] < 0 or c["rc_temp_alpha"] < 0:
        raise ValueError("Invalid timing parameters")
    if c["anneal"]["iters"] < 1 or not isinstance(c["anneal"]["iters"], int):
        raise ValueError("anneal.iters must be a positive integer")
    seen = set()
    for constraint in c["layout_constrains"]:
        pair = constraint["pair"]
        if len(pair) != 2 or pair[0] == pair[1] or not set(pair) <= names:
            raise ValueError("Invalid constraint pair: " + str(pair))
        if constraint["type"] != "same_layer_max_dist" or constraint["max_dist_mm"] <= 0:
            raise ValueError("Unsupported constraint type or distance")
        if constraint.get("layer") not in (None, "top", "bottom") or constraint.get("weight", 1) <= 0:
            raise ValueError("Invalid constraint layer or weight")
        identity = tuple(sorted(pair))
        if identity in seen:
            raise ValueError("Duplicate constraint pair: " + str(pair))
        seen.add(identity)
    for k in ("grid_rows", "grid_cols"):
        value = c[k]
        if not isinstance(value, int) or value < 2 or value & (value - 1):
            raise ValueError(k + " must be a power of two >= 2 for HotSpot")
    if not math.isfinite(c["ambient_c"]) or c["ambient_c"] <= -273.15:
        raise ValueError("Invalid ambient temperature")
    if [s.get("power_layer") for s in c["stack"] if s.get("power_layer") != "none"] != ["bottom", "top"]:
        raise ValueError("stack must include bottom then top powered layers, ordered far side to sink")
    if len({s["name"] for s in c["stack"]}) != len(c["stack"]):
        raise ValueError("Duplicate stack layer name")
    for layer in c["stack"]:
        if any(layer[k] <= 0 or not math.isfinite(layer[k]) for k in ("thickness_um", "conductivity_W_m_K", "heat_capacity_J_m3_K")):
            raise ValueError("Invalid stack material properties")
    if any(not math.isfinite(v) or v <= 0 for v in c["hotspot"].values()):
        raise ValueError("Invalid HotSpot package properties")
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
        if not math.isfinite(m["power_w"]) or m["power_w"] < 0:
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


def bond_bins(c: dict, rects: dict) -> Tuple[float, int, float]:
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


def metrics(c: dict, rects: dict, module_temperatures=None, peak_c=None) -> dict:
    total_n = sum(link[2] for link in c["interconnect"])
    weighted_wire = 0.0
    cross = 0
    rc_cost, rc_weight = 0.0, 0.0
    critical = set(c["critical_modules"])
    path_costs = []
    for a, b, n in c["interconnect"]:
        ax, ay = center(rects[a]); bx, by = center(rects[b])
        distance = abs(ax - bx) + abs(ay - by)
        weighted_wire += n * distance
        vertical = rects[a][4] != rects[b][4]
        if vertical:
            cross += n
        category = "crit_crit" if a in critical and b in critical else ("crit_other" if a in critical or b in critical else "other_other")
        weight = n * c["net_weights"][category]
        temp = max(module_temperatures[a], module_temperatures[b]) if module_temperatures else c["rc_ref_temp"]
        factor = 1 + c["rc_temp_alpha"] * (temp - c["rc_ref_temp"])
        if factor <= 0:
            raise ValueError("Nonpositive RC temperature factor")
        cost = (distance + (c["hbt_vert_um"] * .001 if vertical else 0)) ** 2 * factor
        rc_cost += weight * cost
        rc_weight += weight
        path_costs.append({"pair": [a, b], "signals": n, "category": category,
                           "weight": c["net_weights"][category], "manhattan_mm": distance,
                           "cross_layer": vertical, "rc_temperature_factor": factor,
                           "rc_cost_mm2": cost,
                           "hbt_latency_ps": c["timing"]["hbt_latency_ps"] if vertical else 0})
    area = {z: sum(r[2] * r[3] for r in rects.values() if r[4] == z) for z in LAYERS}
    power = {z: sum(c["modules"][n]["power_w"] for n, r in rects.items() if r[4] == z) for z in LAYERS}
    violations, constraint_penalty = [], 0.0
    for item in c["layout_constrains"]:
        a, b = item["pair"]
        ax, ay = center(rects[a]); bx, by = center(rects[b])
        distance = abs(ax - bx) + abs(ay - by)
        excess = max(0.0, distance - item["max_dist_mm"])
        layer_mismatch = rects[a][4] != rects[b][4]
        wrong_layer = sum(rects[n][4] != item["layer"] for n in (a, b)) if item.get("layer") else 0
        penalty = item.get("weight", 1) * ((excess / item["max_dist_mm"]) ** 2 + int(layer_mismatch) + wrong_layer)
        constraint_penalty += penalty
        violations.append({"pair": [a, b], "distance_mm": distance, "max_dist_mm": item["max_dist_mm"],
                           "excess_mm": excess, "different_layers": layer_mismatch,
                           "requested_layer": item.get("layer"), "wrong_layer_endpoints": wrong_layer,
                           "penalty": penalty, "violated": penalty > 1e-12})
    constraint_penalty /= max(1, len(violations))
    anchor = sum(math.hypot(center(rects[n])[0] - m["anchor"][0], center(rects[n])[1] - m["anchor"][1]) / math.hypot(c["die_width_mm"], c["die_height_mm"])
                 for n, m in c["modules"].items() if m["kind"] == "soft") / len(c["movable_initial_layer"])
    peak_density, bonds, density_limit = bond_bins(c, rects)
    density_over = max(0.0, peak_density / density_limit - 1)
    global_bond_capacity = density_limit * c["die_width_mm"] * c["die_height_mm"]
    global_over = max(0.0, bonds / global_bond_capacity - 1)
    w = c["objective_weights"]
    rc_mean = rc_cost / rc_weight
    budget = cross / total_n * c["timing"]["hbt_latency_ps"] / c["timing"]["clock_period_ps"]
    timing_cost = rc_mean / (c["die_width_mm"] + c["die_height_mm"]) ** 2 + budget
    score = (w["wirelength"] * weighted_wire / total_n / (c["die_width_mm"] + c["die_height_mm"])
             + w["cross_layer"] * cross / total_n
             + w["timing"] * timing_cost
             + w["constraints"] * constraint_penalty
             + (w["temperature"] * max(0, peak_c - c["ambient_c"]) / 10 if peak_c is not None else 0)
             + w["anchor"] * anchor
             + w["layer_balance"] * abs(power["bottom"] - power["top"]) / max(.001, sum(power.values()))
             + 20 * density_over ** 2 + 20 * global_over ** 2)
    return {"score": score, "weighted_wirelength_mm_signals": weighted_wire,
            "mean_weighted_manhattan_mm": weighted_wire / total_n,
            "cross_layer_signals": cross, "estimated_peak_bond_density_per_mm2": peak_density,
            "bond_density_limit_per_mm2": density_limit, "total_bond_capacity": global_bond_capacity,
            "timing_cost_normalized": timing_cost, "rc_quadratic_cost_mm2": rc_mean,
            "mean_hbt_clock_budget_fraction": budget, "interconnect_costs": path_costs,
            "soft_constraint_penalty": constraint_penalty,
            "soft_constraint_violations": sum(v["violated"] for v in violations),
            "constraint_details": violations, "peak_temperature_C": peak_c,
            "temperature_feedback": "HotSpot" if module_temperatures else "reference_temperature_only",
            "layer_area_mm2": area,
            "layer_power_w": power, "anchor_displacement_normalized": anchor,
            "feasible": geometry_ok(c, rects) and density_over < 1e-9 and global_over < 1e-9}


def random_rect(c, name: str, layer: str, rng: random.Random, near: bool = False):
    m = c["modules"][name]
    aspect = rng.choice(c.get("shape_aspects", SHAPES))
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


def mutate(c: dict, current: dict, rng: random.Random) -> Optional[dict]:
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
            aspect = rng.choice(c.get("shape_aspects", SHAPES))
            w = math.sqrt(c["modules"][name]["area_mm2"] * aspect)
            h = c["modules"][name]["area_mm2"] / w
        x = min(max(0, x + rng.gauss(0, .065)), c["die_width_mm"] - w)
        y = min(max(0, y + rng.gauss(0, .065)), c["die_height_mm"] - h)
        candidate = (x, y, w, h, layer)
    trial = {**current, name: candidate}
    return trial if geometry_ok(c, trial) else None


def anneal(c: dict, seed: int, restarts: int, steps: int, candidates: Optional[list] = None,
           start=None, module_temperatures=None):
    best, best_m = None, None
    history = []
    for restart in range(restarts):
        rng = random.Random(seed + restart * 9973)
        current = start.copy() if start is not None and restart == 0 else construct(c, rng)
        current_m = metrics(c, current, module_temperatures)
        if current_m["feasible"] and (best_m is None or current_m["score"] < best_m["score"]):
            best, best_m = current.copy(), current_m.copy()
        restart_best = (current_m["score"], current.copy(), current_m.copy()) if current_m["feasible"] else None
        accepted = 0
        for step in range(steps):
            trial = mutate(c, current, rng)
            if trial is None:
                continue
            trial_m = metrics(c, trial, module_temperatures)
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
    # Retain the previous CLI while making its temperature evaluation real HotSpot.
    import sys
    from explore import main as explore_main
    sys.argv.extend(["--profiles", "balanced", "--selected", "1"])
    explore_main()


if __name__ == "__main__":
    main()
