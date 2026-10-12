"""Source-backed vector layout/Pareto figures and a complete input inventory.

Uses bundled ReportLab chart primitives; PNGs are rendered from the same PDF.
Does not change the simulator or rerun/modify the saved optimization results.
"""
from pathlib import Path
import csv
import json
import hashlib
import math
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, Color
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.lineplots import ScatterPlot
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.graphics import renderPDF
from simulate import Design, PROFILES, check_legal

ROOT = Path(__file__).resolve().parent
DATA = ROOT/"results"
OUT = ROOT/"figures"
OUT.mkdir(exist_ok=True)
PDF_DIR = ROOT/"output/pdf"
PDF_DIR.mkdir(parents=True, exist_ok=True)
manifest = json.loads((DATA/"manifest.json").read_text(encoding="utf-8"))
c = manifest["config"]
winner = manifest["winner"]
assert manifest["source_sha256"] == hashlib.sha256((ROOT/"simulate.py").read_bytes()).hexdigest()


def csvload(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


rows = csvload(DATA/"metrics.csv")
for i, r in enumerate(rows):
    for k in ["power_W", "mean_bips", "peak_C", "frequency_GHz", "nominal_WNS_ps", "route_overflow_tracks"]:
        r[k] = float(r[k])
    r["ok"] = r["feasible"] == "True"
    r["id"] = i+1
before_name = winner["candidate"]+"__baseline"
before = np.load(DATA/(before_name+".npz"))
after = np.load(DATA/(winner["run"]+".npz"))
d = Design(c, winner["candidate"])
assert np.array_equal(before["module_id"], after["module_id"])
assert np.array_equal(before["tier"], after["tier"])
assert np.array_equal(before["edges"], after["edges"])
check_legal(d, before["xy_mm"]); check_legal(d, after["xy_mm"])
base = next(r for r in rows if r["run"] == before_name)
chosen = next(r for r in rows if r["run"] == winner["run"])
pdfmetrics.registerFont(TTFont("YaHei", "C:/Windows/Fonts/msyh.ttc", subfontIndex=0))
pdfmetrics.registerFont(TTFont("YaHeiBold", "C:/Windows/Fonts/msyhbd.ttc", subfontIndex=0))
PALETTE = ["#64748b", "#64748b", "#1d4ed8", "#2563eb", "#b45309", "#c27719", "#ea580c", "#a16207", "#4f46e5", "#7c3aed", "#0e7490", "#0891b2", "#be185d", "#4d7c0f", "#65a30d", "#a21caf"]
SERIES = {"A": "#2563eb", "B": "#b45309", "C": "#9d174d"}
W, H = 1200, 900
pdf_path = PDF_DIR/"cell3d_layouts_and_pareto.pdf"
cv = canvas.Canvas(str(pdf_path), pagesize=(W, H), pageCompression=1)
cv.setTitle("3D IC cell布局前后对比、帕累托前沿与输入口径")
cv.setAuthor("CLIP-3D synthetic experiment")
pages = []


def txt(x, y, value, size=12, color="#172033", bold=False):
    cv.setFont("YaHeiBold" if bold else "YaHei", size)
    cv.setFillColor(HexColor(color))
    cv.drawString(x, y, str(value))


def header(title, subtitle):
    cv.setFillColor(HexColor("#ffffff")); cv.rect(0, 0, W, H, fill=1, stroke=0)
    txt(45, 852, title, 25, bold=True)
    txt(45, 823, subtitle, 12, "#475569")


def footer(note):
    txt(45, 38, note, 11, "#475569")
    txt(45, 19, "来源：cell3d/results 中的已保存数据；合成网表 / 估算参数，不是芯片签核结果。", 10, "#64748b")


def finish(name):
    pages.append(name)
    cv.showPage()


def panel(tier, x, y, size, data=None, title="", blocks=False):
    """True physical rectangle dimensions; no cell subsampling."""
    s = size/c["die_mm"]
    txt(x, y+size+21, title or f"Tier {tier}", 15, bold=True)
    cv.setStrokeColor(HexColor("#a8b3c3")); cv.setLineWidth(.8)
    cv.setFillColor(HexColor("#f8fafc")); cv.rect(x, y, size, size, fill=1, stroke=1)
    for mi, mod in enumerate(d.mods):
        name = mod["name"]
        if d.module_tier[name] != tier:
            continue
        xx, yy, rw, rh = d.regions[name]
        px, py, pw, ph = x+xx*s, y+yy*s, rw*s, rh*s
        color = HexColor(PALETTE[mi])
        cv.setStrokeColor(color); cv.setLineWidth(.65)
        if mod["kind"] == "sram_macro" or blocks:
            cv.setFillColor(Color(color.red, color.green, color.blue, alpha=.12))
            cv.rect(px, py, pw, ph, fill=1, stroke=1)
            txt(px+7, py+ph-20, name, 13, PALETTE[mi], True)
            if mod["kind"] == "sram_macro":
                txt(px+7, py+ph-40, "固定 SRAM 硬宏", 10, "#475569")
            elif size >= 400:
                txt(px+7, py+ph-38, "2100 cells", 9, "#475569")
        else:
            cv.setFillColor(HexColor("#ffffff")); cv.rect(px, py, pw, ph, fill=1, stroke=1)
            ids = np.flatnonzero((data["module_id"] == mi) & data["movable"])
            cv.setFillColor(color)
            cellw, cellh = c["cell_width_um"]/1000, c["cell_height_um"]/1000
            for xxcell, yycell in data["xy_mm"][ids]:
                cv.rect(x+(xxcell-cellw/2)*s, y+(yycell-cellh/2)*s, cellw*s, cellh*s, fill=1, stroke=0)
            txt(px, py-10, name, 9 if size >= 400 else 7.5, PALETTE[mi], True)
    for tick in [0, .4, .8, 1.2, 1.6]:
        txt(x+tick*s-5, y-25, f"{tick:g}", 9, "#64748b")
        txt(x-27, y+tick*s-3, f"{tick:g}", 9, "#64748b")
    txt(x+size/2-25, y-43, "x / mm", 10, "#475569")
    cv.saveState(); cv.translate(x-43, y+size/2-15); cv.rotate(90)
    txt(0, 0, "y / mm", 10, "#475569"); cv.restoreState()


header("01  优化前：估算的模块分层与区域", "A_split 候选；两个 die 采用相同俯视坐标方向，Tier 1 靠近散热器。")
panel(0, 80, 240, 455, blocks=True, title="下层 / Tier 0")
panel(1, 670, 240, 455, blocks=True, title="上层 / Tier 1 · 散热侧")
txt(80, 159, "每层 1.6 × 1.6 mm；逻辑模块区域 0.34 × 0.34 mm；SRAM 宏 0.76 × 0.76 mm。", 13)
txt(80, 132, "后续细化保持这些区域和上下分层固定，优化模块内部的 cell 坐标与网络走线。", 13)
footer("模块区域未铺满 die：保留空白区；这是合成估算起点，不是已有退火最优文件。")
finish("01_initial_modules")

for data, r, stage, name in [(before, base, "优化前", "02_before_cells"), (after, chosen, "优化后", "03_after_cells")]:
    header(f"{('02' if stage=='优化前' else '03')}  {stage}：完整 cell 级布局", f"{r['run']}  |  所有 29,400 个标准单元均按 8 × 4 µm 矩形绘制，没有抽样。")
    panel(0, 80, 245, 455, data=data, title=f"{stage} · 下层 Tier 0")
    panel(1, 670, 245, 455, data=data, title=f"{stage} · 上层 Tier 1")
    txt(80, 157, f"{r['frequency_GHz']:.3f} GHz     {r['power_W']:.3f} W     峰温 {r['peak_C']:.2f}°C     平均 {r['mean_bips']:.3f} BIPS", 15, bold=True)
    txt(80, 126, f"路由 overflow = {r['route_overflow_tracks']:.0f} tracks；{'离散可行' if r['ok'] else '存在拥塞，非可行工作点'}；WNS @ 2 GHz = {r['nominal_WNS_ps']:.1f} ps。", 13)
    footer("功耗与温度对应各自可运行频率；两张图的模块范围、坐标比例、cell 尺寸与颜色完全一致。")
    finish(name)

header("04  同一模块区域内的优化前后对比", "左：初始合法摆放；右：Adam 优化并完成 row/site 合法化。模块分层与边界没有移动。")
for tier, y in [(1, 480), (0, 110)]:
    panel(tier, 235, y, 285, before, f"优化前 · Tier {tier}")
    panel(tier, 775, y, 285, after, f"优化后 · Tier {tier}")
footer("四个面板均显示全部 cell；细节请查看局部放大页或 PDF 矢量原图。")
finish("04_before_after")

header("05  细粒度局部放大：每个小矩形都是一个 cell", "两个模块各 2100 cells；颜色区分模块，白线表示 cell 边界，不代表功率或温度。")
for module_name, y in [("ix", 472), ("rn", 110)]:
    mi = d.mid[module_name]
    rx, ry, rw, rh = d.regions[module_name]
    for data, px, stage in [(before, 225, "优化前"), (after, 760, "优化后")]:
        size = 285
        s = size/rw
        txt(px, y+size+16, f"{module_name} / {stage}", 15, bold=True)
        cv.setFillColor(HexColor("#ffffff")); cv.setStrokeColor(HexColor("#94a3b8"))
        cv.rect(px, y, size, size, fill=1, stroke=1)
        ids = np.flatnonzero((data["module_id"] == mi) & data["movable"])
        cw, ch = c["cell_width_um"]/1000, c["cell_height_um"]/1000
        cv.setStrokeColor(HexColor("#ffffff")); cv.setLineWidth(.22)
        for index in ids:
            xx, yy = data["xy_mm"][index]
            cv.setFillColor(HexColor(PALETTE[mi]))
            cv.rect(px+(xx-rx-cw/2)*s, y+(yy-ry-ch/2)*s, cw*s, ch*s, fill=1, stroke=1)
        txt(px, y-19, "0", 9, "#64748b"); txt(px+size-48, y-19, "340 µm", 9, "#64748b")
footer("Cell：8 × 4 µm；两个布局的 cell ID 一一对应，可在导出的坐标与位移表中追踪。")
finish("05_cell_zoom")


def frontier(keys):
    feasible = [r for r in rows if r["ok"]]
    # Cost keys are minimized, mean_bips maximized; no epsilon changes definition.
    return [r for r in feasible if not any(
        o["mean_bips"] >= r["mean_bips"] and all(o[k] <= r[k] for k in keys)
        and (o["mean_bips"] > r["mean_bips"] or any(o[k] < r[k] for k in keys)) for o in feasible)]


pf3 = frontier(["power_W", "peak_C"])
assert {r["run"] for r in pf3} == set(manifest["pareto"])


def pareto_panel(key, x, y, width, height, title, xmin, xmax, step):
    pf = frontier([key])
    chart = ScatterPlot()
    chart.x, chart.y, chart.width, chart.height = 0, 0, width, height
    chart.leftPadding = chart.rightPadding = chart.topPadding = chart.bottomPadding = 0
    chart.xLabel = chart.yLabel = ""
    chart.lineLabelFormat = None
    chart.outerBorderOn = 0
    groups, styles = [], []
    for a in SERIES:
        for ok in [False, True]:
            subset = [r for r in rows if r["run"][0] == a and r["ok"] == ok]
            if subset:
                groups.append([(r[key], r["mean_bips"]) for r in subset]); styles.append((a, ok))
    chart.data = groups
    chart.xValueAxis.valueMin, chart.xValueAxis.valueMax, chart.xValueAxis.valueStep = xmin, xmax, step
    chart.yValueAxis.valueMin, chart.yValueAxis.valueMax, chart.yValueAxis.valueStep = .86, 1.23, .05
    for axis in [chart.xValueAxis, chart.yValueAxis]:
        axis.rangeRound = "none"
        axis.labelTextFormat = "%.2f" if axis is chart.yValueAxis else "%.1f"
        axis.labels.fontName = "YaHei"; axis.labels.fontSize = 10
        axis.strokeColor = HexColor("#94a3b8")
        axis.visibleGrid = 1; axis.gridStrokeColor = HexColor("#e2e8f0")
    for i, (a, ok) in enumerate(styles):
        symbol = makeMarker("FilledCircle" if ok else "Cross")
        symbol.size = 8 if ok else 9
        if not ok:
            symbol.angle = 45
        symbol.fillColor = HexColor(SERIES[a])
        symbol.strokeColor = HexColor(SERIES[a]); symbol.strokeWidth = 1.5
        chart.lines[i].symbol = symbol; chart.lines[i].strokeWidth = 0
    chart.joinedLines = 0
    drawing = Drawing(width, height); drawing.add(chart)
    renderPDF.draw(drawing, cv, x, y)
    sx = lambda v: x+(v-xmin)/(xmax-xmin)*width
    sy = lambda v: y+(v-.86)/(.37)*height
    txt(x, y+height+20, title, 17, bold=True)
    txt(x+width/2-65, y-39, "功耗 / W" if key == "power_W" else "峰值温度 / °C", 13)
    cv.saveState(); cv.translate(x-47, y+height/2-45); cv.rotate(90)
    txt(0, 0, "平均吞吐率 / BIPS", 12); cv.restoreState()
    ordered = sorted(pf, key=lambda r: r[key])
    cv.setStrokeColor(HexColor("#172033")); cv.setLineWidth(1); cv.setDash(4, 3)
    for a, b in zip(ordered, ordered[1:]):
        cv.line(sx(a[key]), sy(a["mean_bips"]), sx(b[key]), sy(b["mean_bips"]))
    cv.setDash()
    for r in pf:
        cv.circle(sx(r[key]), sy(r["mean_bips"]), 6, stroke=1, fill=0)
    # Adjacent almost-identical baseline/routing-only observations share one label.
    clusters = []
    for r in rows:
        px, py = sx(r[key]), sy(r["mean_bips"])
        target = next((q for q in clusters if math.hypot(px-q[0], py-q[1]) < 8), None)
        if target:
            target[2].append(r["id"])
        else:
            clusters.append([px, py, [r["id"]]])
    occupied = []
    for px, py, ids in sorted(clusters, key=lambda a: -a[1]):
        label = ",".join(str(i) for i in ids)
        tw = pdfmetrics.stringWidth(label, "YaHei", 10)
        selected = None
        for dx, dy in [(9, 9), (-tw-9, 9), (9, -17), (-tw-9, -17), (9, 25), (-tw-9, 25), (15, -32)]:
            box = [px+dx-2, py+dy-3, px+dx+tw+2, py+dy+11]
            if box[0] < x or box[2] > x+width or box[1] < y or box[3] > y+height:
                continue
            if any(not (box[2] < b[0] or b[2] < box[0] or box[3] < b[1] or b[3] < box[1]) for b in occupied):
                continue
            selected = box, dx, dy
            break
        assert selected is not None, (key, ids, "label collision")
        box, dx, dy = selected
        occupied.append(box)
        cv.setStrokeColor(HexColor("#94a3b8")); cv.setLineWidth(.45)
        cv.line(px, py, px+dx+(0 if dx>0 else tw), py+dy+3)
        cv.setFillColor(HexColor("#ffffff")); cv.rect(box[0], box[1], box[2]-box[0], box[3]-box[1], fill=1, stroke=0)
        txt(px+dx, py+dy, label, 10)
    px, py = sx(chosen[key]), sy(chosen["mean_bips"])
    cv.setStrokeColor(HexColor("#172033")); cv.setLineWidth(1.8)
    cv.rect(px-8, py-8, 16, 16, stroke=1, fill=0)
    return pf


header("06  帕累托前沿：功耗、温度与吞吐率", "17 个已评估方案；仅离散可行解参与前沿判定。功耗与峰温对应每个方案各自的可运行频率。")
pf_power = pareto_panel("power_W", 88, 367, 455, 358, "功耗—吞吐率：左上更好", 4.6, 6.5, .3)
pf_temp = pareto_panel("peak_C", 680, 367, 455, 358, "峰温—吞吐率：左上更好", 67., 73., 1.)
txt(80, 299, "● 可行解    × 不可行解    黑圈：该二维前沿    黑框：吞吐率优胜方案 #16    虚线仅辅助阅读", 12)
txt(80, 274, "蓝=A_split；棕=B_critical_local；粉=C_hot_top。重合点共用编号标签；圆圈判定不含不可行点。", 11, "#475569")
for i, r in enumerate(rows):
    col, line = i//6, i%6
    short = r["run"].replace("A_split__", "A/").replace("B_critical_local__", "B/").replace("C_hot_top__", "C/").replace("__seed", "/s")
    txt(80+col*370, 238-line*23, f"{r['id']:02d}  {short}", 11, SERIES[r["run"][0]])
txt(80, 80, f"联合三目标非支配解：{len(pf3)} 个（功耗↓、峰温↓、BIPS↑）；两个二维前沿是分别重算的投影前沿。", 12)
footer("这是17个离散候选的前沿，不是连续设计空间的全局帕累托边界；原始数值与成员关系已导出 CSV。")
finish("06_pareto")
cv.save()

# Also export complete before/after coordinates with cell ID correspondence.
with open(OUT/"cell_before_after.csv", "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(["cell_id", "module", "tier", "movable", "before_x_mm", "before_y_mm", "after_x_mm", "after_y_mm", "displacement_um"])
    for i in range(len(before["xy_mm"])):
        a, b = before["xy_mm"][i], after["xy_mm"][i]
        writer.writerow([i, d.mods[int(before["module_id"][i])]["name"], int(before["tier"][i]), bool(before["movable"][i]), *a, *b, float(np.linalg.norm(b-a)*1000)])
with open(OUT/"pareto_points.csv", "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(["point_id", "run", "feasible", "power_W", "peak_C", "mean_bips", "frequency_GHz", "pareto_power_bips", "pareto_temperature_bips", "pareto_joint_3d"])
    for r in rows:
        writer.writerow([r["id"], r["run"], r["ok"], r["power_W"], r["peak_C"], r["mean_bips"], r["frequency_GHz"], r in pf_power, r in pf_temp, r in pf3])
receipt = dict(before=before_name, after=winner["run"], source_metrics_sha256=hashlib.sha256((DATA/"metrics.csv").read_bytes()).hexdigest(),
               full_cell_count=int(before["movable"].sum()), identical_tiers=True, identical_netlist=True,
               feasible_runs=sum(r["ok"] for r in rows), pareto_power=[r["id"] for r in pf_power],
               pareto_temperature=[r["id"] for r in pf_temp], pareto_joint=[r["id"] for r in pf3],
               pages=pages, pdf=str(pdf_path), source_note="Existing saved estimates; no new simulation performed.")
(OUT/"figure_manifest.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(receipt, ensure_ascii=False, indent=2))
