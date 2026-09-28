"""Scale every module's assumed area while preserving hard-macro aspect ratios."""
import argparse
import copy
import json
import math
from pathlib import Path

from optimize import load_config, validate


def scale_config(original: dict, factor: float) -> dict:
    c = copy.deepcopy(original)
    c["provenance"] += f" Enlarged all synthetic module areas by {factor:g}x."
    c["requested_area_multiplier"] = 3.0
    c["applied_area_multiplier"] = factor
    for name, module in c["modules"].items():
        if module["kind"] == "soft":
            module["area_mm2"] *= factor
        else:
            x, y, w, h = module["rect"]
            w *= math.sqrt(factor)
            h *= math.sqrt(factor)
            if name == "l2_b1":
                # The original right macro coordinate was itself synthetic.
                x = c["die_width_mm"] - w - .035
            module["rect"] = [x, y, w, h]
    validate(c)
    return c


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--factor", type=float, default=1.7)
    args = parser.parse_args()
    original = load_config(args.source)
    base = sum(m.get("area_mm2", m.get("rect", [0, 0, 0, 0])[2] * m.get("rect", [0, 0, 0, 0])[3]) for m in original["modules"].values())
    cap = 2 * original["die_area_limit_mm2"] * original["area_margin"]
    if base * args.factor > cap + 1e-9:
        raise SystemExit(f"Infeasible by area alone: {base:.4f} x {args.factor:g} = {base*args.factor:.4f} mm2 > {cap:.4f} mm2 capacity")
    c = scale_config(original, args.factor)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}: {args.factor:g}x, {base*args.factor:.4f}/{cap:.4f} mm2")


if __name__ == "__main__":
    main()
