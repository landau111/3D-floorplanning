"""Thermal feedback search with real HotSpot and multiobjective Pareto screening."""

import argparse
import copy
import csv
import json
import math
import random
import shutil
from pathlib import Path

from optimize import anneal, load_config, metrics, mutate, validate, write_svg
from thermal import find_hotspot, run_hotspot, temperature_svg
from constraints import constraint_feasibility


# Multipliers on user-configured weights. Every actual set is saved with results.
PROFILES = {
    "balanced": {},
    "wire": {"wirelength": 2.5, "temperature": .4},
    "thermal": {"temperature": 4.0, "wirelength": .6},
    "bond": {"cross_layer": 4.0, "timing": .7},
    "timing": {"timing": 3.0, "temperature": .5},
    "constraint": {"constraints": 3.0, "wirelength": .6},
}
OBJECTIVE_KEYS = ("mean_weighted_manhattan_mm", "cross_layer_signals", "timing_cost_normalized",
                  "soft_constraint_penalty", "peak_temperature_C")


def objectives(candidate):
    return tuple(candidate["metrics"][key] for key in OBJECTIVE_KEYS)


def pareto_flags(candidates):
    points = [objectives(c) for c in candidates]
    return [not any(j != i and all(v <= u+1e-10 for v,u in zip(p,point)) and
                    any(v < u-1e-10 for v,u in zip(p,point))
                    for j,p in enumerate(points)) for i,point in enumerate(points)]


def select_candidates(candidates, flags, count):
    points = [objectives(c) for c in candidates]
    dimensions = len(OBJECTIVE_KEYS)
    low = [min(p[k] for p in points) for k in range(dimensions)]
    high = [max(p[k] for p in points) for k in range(dimensions)]
    normalized = [tuple((p[k]-low[k])/max(1e-10, high[k]-low[k]) for k in range(dimensions)) for p in points]
    front = [i for i,flag in enumerate(flags) if flag]
    chosen = []
    # Show best constraints, best temperature, best timing and a balanced tradeoff.
    for k in (3,4,2):
        index = min(front, key=lambda i: (normalized[i][k], sum(normalized[i])))
        if index not in chosen and len(chosen) < count:
            chosen.append(index)
    if len(chosen) < count:
        index = min(front, key=lambda i: sum(normalized[i]))
        if index not in chosen:
            chosen.append(index)
    while len(chosen) < min(count,len(front)):
        remaining = [i for i in front if i not in chosen]
        chosen.append(max(remaining, key=lambda i: min(sum((normalized[i][k]-normalized[j][k])**2
                                                                       for k in range(dimensions)) for j in chosen)))
    return chosen  # Never label dominated fillers as an optimal selection.


def pareto_svg(path, candidates, flags, selected):
    points = [objectives(c) for c in candidates]
    panels = [(0, "Weighted Manhattan length (mm)"), (1, "Cross-layer signals"),
              (2, "Timing cost (normalized proxy)"), (3, "Soft constraint penalty")]
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="950">',
           '<style>text{font:13px Arial,sans-serif}.title{font-size:17px;font-weight:bold}</style>',
           '<text class="title" x="25" y="25">Five-objective Pareto screening / real HotSpot</text>']
    colors = ("#d62828", "#0a9396", "#6a4c93", "#f77f00", "#3a86ff", "#e76f51")
    for panel,(xi,xlabel) in enumerate(panels):
        left,top,width,height = 65+(panel%2)*555, 65+(panel//2)*440, 420,320
        xmin,xmax = min(p[xi] for p in points),max(p[xi] for p in points)
        ymin,ymax = min(p[4] for p in points),max(p[4] for p in points)
        xspan,yspan = max(1e-10,xmax-xmin),max(1e-10,ymax-ymin)
        out.append('<rect x="{}" y="{}" width="{}" height="{}" fill="#f7fafc" stroke="#333"/>'.format(left,top,width,height))
        for i,point in enumerate(points):
            x,y = left+(point[xi]-xmin)/xspan*width, top+height-(point[4]-ymin)/yspan*height
            color = colors[selected.index(i)%len(colors)] if i in selected else ("#2364aa" if flags[i] else "#b8c4cc")
            radius = 7 if i in selected else (4 if flags[i] else 3)
            out.append('<circle cx="{:.2f}" cy="{:.2f}" r="{}" fill="{}" stroke="white"><title>candidate {}: {} / {}</title></circle>'.format(x,y,radius,color,i+1,candidates[i]["profile"],point))
            if i in selected:
                out.append('<text x="{:.2f}" y="{:.2f}">L{}</text>'.format(x+8,y-8,selected.index(i)+1))
        out.append('<text x="{}" y="{}">{}: {:.4g} to {:.4g}</text>'.format(left,top+height+25,xlabel,xmin,xmax))
        out.append('<text x="{}" y="{}">Peak temperature (C): {:.3f} to {:.3f}</text>'.format(left,top+height+45,ymin,ymax))
    out.append('<text x="30" y="930">Blue: 5-D nondominated; gray: dominated; colors: selected / assumed power, stack and package</text></svg>')
    path.write_text("\n".join(out),encoding="utf-8")


def thermal_search(config, executable, output, steps, restarts, rounds, profiles):
    """Cheap inner geometry SA, exact outer HotSpot feedback and acceptance.

    Inner proposals use frozen last-evaluated module temperatures for RC weights;
    only current-layout HotSpot temperatures participate in outer acceptance,
    final metrics and Pareto screening. No temperature prediction is made.
    """
    pool, cache, history = [], {}, []
    for profile_index,profile in enumerate(profiles):
        c = copy.deepcopy(config)
        for key,multiplier in PROFILES[profile].items():
            c["objective_weights"][key] *= multiplier
        print("{}: weights {}".format(profile,c["objective_weights"]),flush=True)
        for restart in range(restarts):
            seed = c["search"]["seed"] + profile_index*100003 + restart*9973
            rng = random.Random(seed)
            current, current_score = None, None
            temperatures = None
            for iteration in range(rounds):
                start = current.copy() if current else None
                # Perturb several modules before refinement to escape a local basin.
                if start:
                    for _ in range(30):
                        proposal = mutate(c,start,rng)
                        if proposal is not None:
                            start = proposal
                # Periodic fresh packings explore layer assignments beyond local moves.
                if iteration and iteration % 8 == 0:
                    start = None
                proposal = None
                for attempt in range(5):
                    try:
                        proposal,_,_ = anneal(c,seed+iteration*7919+attempt*1543,1,steps,
                                              start=start,module_temperatures=temperatures)
                        break
                    except RuntimeError:
                        start = None
                if proposal is None:
                    raise RuntimeError("No legal packing found for profile " + profile)
                fingerprint = tuple((name,tuple(r)) for name,r in sorted(proposal.items()))
                cached = fingerprint in cache
                if not cached:
                    thermal = run_hotspot(executable,config,proposal,output/"hotspot_pool"/"candidate_{:04d}".format(len(pool)+1))
                    canonical = metrics(config,proposal,thermal["module_peak_C"],thermal["peak_C"])
                    item = {"profile":profile,"rects":proposal,"metrics":canonical,"thermal":thermal,
                            "iteration":iteration+1,"restart":restart+1}
                    cache[fingerprint] = len(pool)
                    pool.append(item)
                item = pool[cache[fingerprint]]
                thermal = item["thermal"]
                score = metrics(c,proposal,thermal["module_peak_C"],thermal["peak_C"])["score"]
                temperature = .10*(.005/.10)**(iteration/max(1,rounds-1))
                accept = current_score is None or score < current_score or rng.random() < math.exp(min(0,(current_score-score)/temperature))
                if accept:
                    current,current_score,temperatures = proposal.copy(),score,thermal["module_peak_C"]
                record = {"profile":profile,"restart":restart+1,"round":iteration+1,
                          "candidate":cache[fingerprint]+1,"hotspot_cache_hit":cached,"accepted":accept,
                          "score":score,"peak_temperature_C":thermal["peak_C"],
                          "soft_constraint_violations":item["metrics"]["soft_constraint_violations"]}
                history.append(record)
                print("{} restart {} round {}/{}: {:.3f} C, {} soft violations, {}".format(
                    profile,restart+1,iteration+1,rounds,thermal["peak_C"],
                    record["soft_constraint_violations"],"accepted" if accept else "rejected"),flush=True)
    return pool,history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config",type=Path)
    parser.add_argument("--output",type=Path,default=Path(__file__).parent/"local_results")
    parser.add_argument("--hotspot-exe")
    parser.add_argument("--steps",type=int)
    parser.add_argument("--restarts",type=int)
    parser.add_argument("--thermal-rounds",type=int)
    parser.add_argument("--selected",type=int,default=4)
    parser.add_argument("--profiles",default=",".join(PROFILES))
    args = parser.parse_args()
    config = load_config(args.config)
    validate(config)
    feasibility = constraint_feasibility(config)
    if not feasibility["all_soft_constraints_necessarily_possible"]:
        print("Some soft preferences are geometrically impossible; see constraint_feasibility.json",flush=True)
    executable = find_hotspot(args.hotspot_exe)
    steps = args.steps if args.steps is not None else config["search"]["steps_per_restart"]
    restarts = args.restarts if args.restarts is not None else config["search"]["restarts"]
    rounds = args.thermal_rounds if args.thermal_rounds is not None else config["anneal"]["iters"]
    profiles = args.profiles.split(",")
    if min(steps,restarts,rounds,args.selected) <= 0 or any(p not in PROFILES for p in profiles) or len(set(profiles)) != len(profiles):
        parser.error("Positive search budgets and distinct known profiles required")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True,exist_ok=True)
    # New runs in the same output directory must not mix with previous selected layouts.
    if (args.output/"manifest.json").exists():
        raise RuntimeError("Output already contains results. Use a new --output directory to preserve provenance.")
    (args.output/"effective_config.json").write_text(json.dumps(config,indent=2),encoding="utf-8")
    (args.output/"constraint_feasibility.json").write_text(json.dumps(feasibility,indent=2),encoding="utf-8")
    shutil.copyfile(str(args.config),str(args.output/"input_config.yaml"))
    pool,history = thermal_search(config,executable,args.output,steps,restarts,rounds,profiles)
    flags = pareto_flags(pool)
    selected = select_candidates(pool,flags,args.selected)
    if len(profiles) == 1 and args.selected == 1:
        selected = [min((i for i,flag in enumerate(flags) if flag),key=lambda i:pool[i]["metrics"]["score"])]
    lo = min(v for i in selected for layer in pool[i]["thermal"]["temperature_C"] for row in layer for v in row)
    hi = max(v for i in selected for layer in pool[i]["thermal"]["temperature_C"] for row in layer for v in row)
    selections = []
    for rank,i in enumerate(selected,1):
        item = pool[i]
        folder = args.output/"layout_{:02d}".format(rank)
        folder.mkdir(exist_ok=True)
        write_svg(folder/"layout.svg",config,item["rects"])
        thermal = item["thermal"]
        temperature_svg(folder/"temperature.svg",config,item["rects"],thermal,(lo,hi))
        shutil.copytree(thermal["input_directory"],str(folder/"hotspot"))
        payload = {"profile":item["profile"],"candidate":i+1,"pareto":flags[i],"metrics":item["metrics"],
                   "thermal":{k:v for k,v in thermal.items() if k != "temperature_C"},
                   "modules":{n:dict(zip(("x_mm","y_mm","w_mm","h_mm","layer"),r)) for n,r in item["rects"].items()}}
        (folder/"layout.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
        with (folder/"temperature.csv").open("w",newline="",encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["layer","row_from_bottom","column_from_left","temperature_C","backend"])
            for z,layer in enumerate(thermal["temperature_C"]):
                for row,values in enumerate(layer):
                    for col,value in enumerate(values):
                        writer.writerow([("bottom","top")[z],row,col,value,"HotSpot"])
        with (folder/"constraint_violations.csv").open("w",newline="",encoding="utf-8") as f:
            writer = csv.DictWriter(f,fieldnames=list(item["metrics"]["constraint_details"][0]) if item["metrics"]["constraint_details"] else ["pair","violated"])
            writer.writeheader(); writer.writerows(item["metrics"]["constraint_details"])
        selections.append({"layout":folder.name,"candidate":i+1,"profile":item["profile"],
                           "peak_temperature_C":thermal["peak_C"],
                           "soft_constraint_violations":item["metrics"]["soft_constraint_violations"],
                           "objectives":dict(zip(OBJECTIVE_KEYS,objectives(item)))})
    with (args.output/"pareto_candidates.csv").open("w",newline="",encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate","profile","pareto","selected_rank"]+list(OBJECTIVE_KEYS)+["soft_constraint_violations","score"])
        for i,item in enumerate(pool):
            writer.writerow([i+1,item["profile"],flags[i],selected.index(i)+1 if i in selected else ""]+
                            list(objectives(item))+[item["metrics"]["soft_constraint_violations"],item["metrics"]["score"]])
    pareto_svg(args.output/"pareto.svg",pool,flags,selected)
    manifest = {"config":args.config.name,"candidate_count":len(pool),"pareto_count":sum(flags),
                "temperature_backend":"HotSpot","selected":selections,"pareto_objectives":list(OBJECTIVE_KEYS),
                "search":{"thermal_rounds":rounds,"geometry_moves_per_round":steps,"restarts":restarts,
                          "profiles":profiles,"profile_weight_multipliers":PROFILES,"hotspot_calls":len(pool)},
                "model_limits":"Synthetic module powers, stack and package. RC L^2 is a ranking cost, not physical delay. No IPC/BIPS, routing or STA. Soft constraints may remain violated; inspect per-pair reports.",
                "thermal_feedback":"Exact HotSpot outer acceptance; inner geometric proposals use frozen last module temperatures for RC weights.",
                "power_W":sum(m["power_w"] for m in config["modules"].values()),
                "constraint_feasibility":feasibility}
    (args.output/"search_history.json").write_text(json.dumps(history,indent=2),encoding="utf-8")
    (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps({"candidates":len(pool),"pareto":sum(flags),"selected":len(selected),"thermal_backend":"HotSpot","output":str(args.output)}))


if __name__ == "__main__":
    main()
