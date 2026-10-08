"""Dated result directories and portable module coordinate exports."""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path


RESULT_ROOT = Path(__file__).resolve().parents[1] / "result"
SHANGHAI = timezone(timedelta(hours=8))
COORDINATE_FIELDS = ("module", "layer", "x_mm", "y_mm", "w_mm", "h_mm",
                     "center_x_mm", "center_y_mm")


def default_output(action="explore", root=None, now=None):
    """Use Shanghai dates consistently on Windows and Linux; preserve old runs."""
    moment = now or datetime.now(SHANGHAI)
    moment = moment.replace(tzinfo=SHANGHAI) if moment.tzinfo is None else moment.astimezone(SHANGHAI)
    day = Path(root or RESULT_ROOT) / moment.strftime("%Y-%m-%d")
    name = moment.strftime("%H%M%S") + "_" + action
    output = day / name
    suffix = 2
    while output.exists():
        output = day / (name + "_{:02d}".format(suffix))
        suffix += 1
    return output


def coordinate_rows(modules):
    """Coordinates in mm, origin at the die's bottom left, per physical layer."""
    for name, module in sorted(modules.items()):
        yield dict(module=name, layer=module["layer"],
                   x_mm=module["x_mm"], y_mm=module["y_mm"],
                   w_mm=module["w_mm"], h_mm=module["h_mm"],
                   center_x_mm=module["x_mm"] + module["w_mm"] / 2,
                   center_y_mm=module["y_mm"] + module["h_mm"] / 2)


def write_coordinates(folder, modules):
    with (folder / "module_coordinates.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COORDINATE_FIELDS)
        writer.writeheader()
        writer.writerows(coordinate_rows(modules))


def write_coordinate_summary(output, layouts):
    """Export all selected modules in one table for comparing placements."""
    with (output / "all_module_coordinates.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("layout", "candidate", "profile") + COORDINATE_FIELDS)
        writer.writeheader()
        for layout, payload in layouts:
            for row in coordinate_rows(payload["modules"]):
                row.update(layout=layout, candidate=payload["candidate"], profile=payload["profile"])
                writer.writerow(row)


def write_result_index(output, selected):
    lines = ["# 布局探索结果", "", "- [帕累托图](pareto.svg)",
             "- [所有候选指标](pareto_candidates.csv)",
             "- [所有入选方案的模块坐标](all_module_coordinates.csv)",
             "- [运行配置和记录](manifest.json)", "",
             "坐标单位 mm；原点在各层 die 的左下角。x/y 为模块左下角，w/h 为宽高，center_x/center_y 为中心。",
             "bottom 表示下层，top 表示上层。所有温度图共用色标。", "",
             "| 方案 | 最高温度℃ | 布局图 | 温度图 | 模块坐标 |", "| --- | ---: | --- | --- | --- |"]
    for item in selected:
        name = item["layout"]
        lines.append("| {} | {:.3f} | [布局]({}/layout.svg) | [温度]({}/temperature.svg) | [坐标]({}/module_coordinates.csv) |".format(
            name, item["peak_temperature_C"], name, name, name))
    lines += ["", "结果为当前模型和搜索预算下的代表性非支配候选，不保证全局最优；逐条约束见各方案的 constraint_violations.csv。", ""]
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")
