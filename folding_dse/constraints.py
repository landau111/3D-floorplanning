"""Necessary-condition checks for user soft placement preferences."""

from optimize import SHAPES


def constraint_feasibility(config):
    capacity = config["die_area_limit_mm2"] * config["area_margin"]
    layer_requirements = {}
    for layer in ("bottom", "top"):
        modules = set(config["fixed_" + layer])
        for constraint in config["layout_constrains"]:
            if constraint.get("layer") == layer:
                modules.update(constraint["pair"])
        area = sum(config["modules"][name].get("area_mm2", 0) +
                   (config["modules"][name]["rect"][2]*config["modules"][name]["rect"][3]
                    if config["modules"][name]["kind"] == "hard" else 0) for name in modules)
        layer_requirements[layer] = {"preferred_modules": sorted(modules), "required_area_mm2":area,
                                     "capacity_mm2":capacity,"area_necessary_condition_met":area <= capacity+1e-9}
    distances = []
    def minimum_dimensions(name):
        module = config["modules"][name]
        if module["kind"] == "hard":
            return module["rect"][2:4]
        import math
        shapes = [(math.sqrt(module["area_mm2"]*s), math.sqrt(module["area_mm2"]/s)) for s in config.get("shape_aspects", SHAPES)]
        shapes = [(w,h) for w,h in shapes if w <= config["die_width_mm"] and h <= config["die_height_mm"]]
        if not shapes:
            return float("inf"),float("inf")
        return min(w for w,h in shapes),min(h for w,h in shapes)
    for constraint in config["layout_constrains"]:
        a,b = constraint["pair"]
        wa,ha = minimum_dimensions(a); wb,hb = minimum_dimensions(b)
        # Nonoverlap requires separation in at least one axis. This is only a lower
        # bound: it ignores other modules, die edges, hard anchors and packing.
        lower = min((wa+wb)/2,(ha+hb)/2)+config["module_gap_mm"]
        distances.append({"pair":[a,b],"max_dist_mm":constraint["max_dist_mm"],
                          "minimum_center_manhattan_lower_bound_mm":lower,
                          "distance_necessary_condition_met":lower <= constraint["max_dist_mm"]+1e-9})
    possible = all(v["area_necessary_condition_met"] for v in layer_requirements.values()) and all(v["distance_necessary_condition_met"] for v in distances)
    return {"all_soft_constraints_necessarily_possible":possible,"layer_preferences":layer_requirements,
            "pair_distance_lower_bounds":distances,
            "aspect_ratios":list(config.get("shape_aspects", SHAPES)),
            "note":"Passing these necessary conditions does not prove simultaneous feasibility. Failure proves some soft violations are unavoidable under the configured geometry/shape model."}
