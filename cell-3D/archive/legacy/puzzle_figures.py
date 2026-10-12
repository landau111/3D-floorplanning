"""Render the new nonrectangular territories, full cells and old/new comparisons."""
from pathlib import Path
import csv,json,hashlib,subprocess,shutil
import numpy as np
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor,Color
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.lineplots import ScatterPlot
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.graphics import renderPDF
from simulate import Design

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"puzzle_figures"; OUT.mkdir(exist_ok=True)
P=ROOT/"output/pdf/puzzle_layouts.pdf";P.parent.mkdir(parents=True,exist_ok=True)
m=json.loads((ROOT/"puzzle_results/manifest.json").read_text(encoding="utf-8"))
old=json.loads((ROOT/"results/manifest.json").read_text(encoding="utf-8"))
assert hashlib.sha256((ROOT/"puzzle.py").read_bytes()).hexdigest()==m["source_sha256"]
c=m["physical_config"];d=Design(c,m["config"]["base_candidate"])
new=np.load(ROOT/"puzzle_results"/(m["winner"]["run"]+".npz"))
prev=np.load(ROOT/"results"/(old["winner"]["run"]+".npz"))
assert np.array_equal(new["edges"],prev["edges"])
assert np.array_equal(new["tier"],prev["tier"])
assert np.array_equal(new["module_id"],prev["module_id"])
labels=new["labels"];g=labels.shape[1];tile=c["die_mm"]/g
colors=["#64748b","#64748b","#1d4ed8","#2563eb","#b45309","#c27719","#ea580c","#a16207","#4f46e5","#7c3aed","#0e7490","#0891b2","#be185d","#4d7c0f","#65a30d","#a21caf"]
pdfmetrics.registerFont(TTFont("YaHei","C:/Windows/Fonts/msyh.ttc",subfontIndex=0))
pdfmetrics.registerFont(TTFont("YaHeiBold","C:/Windows/Fonts/msyhbd.ttc",subfontIndex=0))
cv=canvas.Canvas(str(P),pagesize=(1200,900),pageCompression=1)
cv.setTitle("拼图式模块分区与细粒度cell布局")
pages=[]

def text(x,y,s,size=12,color="#172033",bold=False):
    cv.setFont("YaHeiBold" if bold else "YaHei",size);cv.setFillColor(HexColor(color));cv.drawString(x,y,str(s))

def header(title,subtitle):
    cv.setFillColor(HexColor("#ffffff"));cv.rect(0,0,1200,900,fill=1,stroke=0)
    text(45,850,title,25,bold=True);text(45,820,subtitle,12,"#475569")

def footer(note):
    text(45,38,note,11,"#475569")
    text(45,19,"合成网表 / 估算物理模型；不是真实芯片签核。浅色背景是模块归属，深色小矩形才是cell。",10,"#64748b")

def finish(name):pages.append(name);cv.showPage()

boundary_records=[]
for z in range(2):
    for mi in np.unique(labels[z]):
        if mi<0:continue
        edges=[]
        for y,x in zip(*np.nonzero(labels[z]==mi)):
            for yy,xx,a,b in [(y-1,x,(x,y),(x+1,y)),(y+1,x,(x,y+1),(x+1,y+1)),
                               (y,x-1,(x,y),(x,y+1)),(y,x+1,(x+1,y),(x+1,y+1))]:
                if not (0<=yy<g and 0<=xx<g and labels[z,yy,xx]==mi):
                    edges.append([[a[0]*tile,a[1]*tile],[b[0]*tile,b[1]*tile]])
        boundary_records.append(dict(module=d.mods[mi]["name"],module_id=int(mi),tier=z,boundary_segments_mm=edges))
(OUT/"module_boundaries.json").write_text(json.dumps(boundary_records,ensure_ascii=False,indent=2),encoding="utf-8")

def panel(z,px,py,size,mode="territory",title=""):
    scale=size/c["die_mm"]
    text(px,py+size+20,title,14,bold=True)
    cv.setFillColor(HexColor("#f1f5f9"));cv.setStrokeColor(HexColor("#94a3b8"));cv.setLineWidth(.7)
    cv.rect(px,py,size,size,fill=1,stroke=1)
    if mode!="old":
        for mi in np.unique(labels[z]):
            if mi<0:continue
            col=HexColor(colors[mi]);strength=.32 if mode=="territory" else .13
            cv.setFillColor(Color(1-strength+strength*col.red,1-strength+strength*col.green,1-strength+strength*col.blue))
            for y,x in zip(*np.nonzero(labels[z]==mi)):
                cv.rect(px+x*tile*scale,py+y*tile*scale,tile*scale+.04,tile*scale+.04,fill=1,stroke=0)
        for record in boundary_records:
            if record["tier"]!=z:continue
            cv.setStrokeColor(HexColor(colors[record["module_id"]]));cv.setLineWidth(.75)
            for a,b in record["boundary_segments_mm"]:
                cv.line(px+a[0]*scale,py+a[1]*scale,px+b[0]*scale,py+b[1]*scale)
    else:
        for mi,mod in enumerate(d.mods):
            if mod["kind"]!="logic" or d.module_tier[mod["name"]]!=z:continue
            x,y,w,h=d.regions[mod["name"]]
            cv.setFillColor(HexColor("#ffffff"));cv.setStrokeColor(HexColor(colors[mi]))
            cv.rect(px+x*scale,py+y*scale,w*scale,h*scale,fill=1,stroke=1)
    macro=d.regions[f"l2_b{z}"]
    x,y,w,h=macro
    cv.setFillColor(HexColor("#cbd5e1"));cv.setStrokeColor(HexColor("#64748b"))
    cv.rect(px+x*scale,py+y*scale,w*scale,h*scale,fill=1,stroke=1)
    text(px+(x+.04)*scale,py+(y+h-.09)*scale,f"l2_b{z}  固定硬宏",12 if size>350 else 10,"#475569",True)
    if mode in ["cells","old"]:
        data=new if mode=="cells" else prev
        for mi,mod in enumerate(d.mods):
            if mod["kind"]!="logic" or d.module_tier[mod["name"]]!=z:continue
            ids=np.flatnonzero((data["module_id"]==mi)&data["movable"])
            cv.setFillColor(HexColor(colors[mi]))
            w,h=c["cell_width_um"]/1000,c["cell_height_um"]/1000
            for x,y in data["xy_mm"][ids]:
                cv.rect(px+(x-w/2)*scale,py+(y-h/2)*scale,w*scale,h*scale,fill=1,stroke=0)
    for mi,mod in enumerate(d.mods):
        if mod["kind"]!="logic" or d.module_tier[mod["name"]]!=z:continue
        if mode=="old":
            x,y,w,h=d.regions[mod["name"]]; pos=np.array([x,y-.032])
        else:
            yy,xx=np.nonzero(labels[z]==mi)
            pts=np.column_stack([(xx+.5)*tile,(yy+.5)*tile])
            pos=pts[np.argmin(((pts-pts.mean(0))**2).sum(1))]
        name=mod["name"];fs=11 if size>350 else 8
        tw=pdfmetrics.stringWidth(name,"YaHeiBold",fs)
        lx=px+pos[0]*scale-(tw/2 if mode!="old" else 0)
        ly=py+pos[1]*scale
        if mode!="old":
            cv.setFillColor(Color(1,1,1,alpha=.9));cv.rect(lx-3,ly-3,tw+6,fs+6,fill=1,stroke=0)
        text(lx,ly,name,fs,colors[mi],True)
    for tick in [0,.4,.8,1.2,1.6]:
        text(px+tick*scale-5,py-23,f"{tick:g}",9,"#64748b")
        text(px-28,py+tick*scale-3,f"{tick:g}",9,"#64748b")
    text(px+size/2-20,py-40,"x / mm",10,"#475569")

header("01  拼图式模块区域：覆盖原来的留白区", "上下层不变，逻辑模块不再受原矩形围栏限制；灰色为固定SRAM及20µm保护区。")
panel(0,80,240,455,"territory","下层 / Tier 0")
panel(1,670,240,455,"territory","上层 / Tier 1 · 散热侧")
text(80,151,"可用区域归属覆盖率 100%  |  14个模块均连通且无孔洞  |  最大长宽比 2.10",15,bold=True)
text(80,120,"实际 cell 面积利用率为 24.5%（非宏保护区内）；背景填色不代表新增了 cell。",13)
footer("40µm分区网格；模块边界可以是非矩形，硬宏、层分配和cell数量保持不变。")
finish("01_puzzle_regions")

header("02  旧矩形围栏版 → 新拼图区域版", "同一网表和cell ID；左侧为上一轮最优，右侧为本轮可行方案中的吞吐率最优。")
for z,y in [(1,480),(0,110)]:
    panel(z,235,y,285,"old",f"矩形围栏版 / Tier {z}")
    panel(z,775,y,285,"cells",f"拼图版 / Tier {z}")
footer(f"{m['winner']['cells_outside_old_rectangle']:,} / 29,400 cells 已移出原矩形范围；全部cell按真实模型尺寸绘制。")
finish("02_puzzle_before_after")

header("03  新的完整 cell 布局", "深色小矩形：8×4µm标准单元；浅色：该模块可用区域；白隙：尚未占用的合法位置。")
panel(0,80,240,455,"cells","下层 / Tier 0")
panel(1,670,240,455,"cells","上层 / Tier 1")
w=m["winner"]
text(80,155,f"{w['frequency_GHz']:.3f} GHz   ·   {w['power_W']:.3f} W   ·   峰温 {w['peak_C']:.2f}°C   ·   {w['mean_bips']:.3f} BIPS",15,bold=True)
text(80,123,f"估算路由 overflow={w['route_overflow_tracks']:.0f}；2GHz下 WNS={w['nominal_WNS_ps']:.1f} ps，仍未满足2GHz时序。",13)
footer("区域完整覆盖不等于单元100%利用率；在现有die、宏和cell面积不变时，利用率由面积比决定。")
finish("03_puzzle_cells")

def readmetrics(path):
    with open(path,encoding="utf-8-sig") as f:rows=list(csv.DictReader(f))
    for r in rows:
        for k in ["power_W","peak_C","mean_bips"]:r[k]=float(r[k])
        r["ok"]=r["feasible"]=="True"
    return rows
rows=readmetrics(ROOT/"results/metrics.csv")+readmetrics(ROOT/"puzzle_results/metrics.csv")
def plot(key,px,py,xmin,xmax,xstep,title):
    width,height=450,380
    chart=ScatterPlot();chart.x=chart.y=0;chart.width=width;chart.height=height
    chart.leftPadding=chart.rightPadding=chart.topPadding=chart.bottomPadding=0
    chart.xLabel=chart.yLabel="";chart.lineLabelFormat=None;chart.outerBorderOn=0
    chart.data=[]; groups=[]
    for puzzle in [False,True]:
        for ok in [False,True]:
            group=[r for r in rows if r["run"].startswith("puzzle")==puzzle and r["ok"]==ok]
            if group:chart.data.append([(r[key],r["mean_bips"]) for r in group]);groups.append((puzzle,ok))
    chart.xValueAxis.valueMin=xmin;chart.xValueAxis.valueMax=xmax;chart.xValueAxis.valueStep=xstep
    chart.yValueAxis.valueMin=.86;chart.yValueAxis.valueMax=1.24;chart.yValueAxis.valueStep=.05
    for a in [chart.xValueAxis,chart.yValueAxis]:
        a.rangeRound="none";a.labelTextFormat="%.2f" if a is chart.yValueAxis else "%.1f"
        a.labels.fontName="YaHei";a.labels.fontSize=10;a.visibleGrid=1;a.gridStrokeColor=HexColor("#e2e8f0")
    for i,(puzzle,ok) in enumerate(groups):
        symbol=makeMarker("FilledCircle" if ok else "Cross");symbol.size=9 if puzzle else 6
        symbol.fillColor=symbol.strokeColor=HexColor("#d97706" if puzzle else "#64748b")
        if not ok:symbol.angle=45
        chart.lines[i].symbol=symbol;chart.lines[i].strokeWidth=0
    chart.joinedLines=0
    draw=Drawing(width,height);draw.add(chart);renderPDF.draw(draw,cv,px,py)
    sx=lambda a:px+(a-xmin)/(xmax-xmin)*width
    sy=lambda a:py+(a-.86)/.38*height
    front=[r for r in rows if r["ok"] and not any(o["ok"] and o[key]<=r[key] and o["mean_bips"]>=r["mean_bips"] and
                       (o[key]<r[key] or o["mean_bips"]>r["mean_bips"]) for o in rows)]
    front=sorted(front,key=lambda r:r[key])
    cv.setStrokeColor(HexColor("#172033"));cv.setDash(4,3);cv.setLineWidth(1)
    for a,b in zip(front,front[1:]):cv.line(sx(a[key]),sy(a["mean_bips"]),sx(b[key]),sy(b["mean_bips"]))
    cv.setDash()
    for r in front:cv.circle(sx(r[key]),sy(r["mean_bips"]),6,stroke=1,fill=0)
    for r in rows:
        if not r["run"].startswith("puzzle"):continue
        offset={"balanced":(-90,12),"timing":(9,9),"thermal":(9,-21)}[r["profile"]]
        xx,yy=sx(r[key]),sy(r["mean_bips"])
        cv.setStrokeColor(HexColor("#94a3b8"));cv.line(xx,yy,xx+offset[0],yy+offset[1])
        text(xx+offset[0],yy+offset[1],r["profile"],10,"#b45309",True)
    text(px,py+height+22,title,17,bold=True)
    text(px+150,py-38,"功耗 / W" if key=="power_W" else "最高温度 / °C",12)
    cv.saveState();cv.translate(px-45,py+120);cv.rotate(90);text(0,0,"平均吞吐率 / BIPS",12);cv.restoreState()
    return [r["run"] for r in front]
header("04  新旧方案联合帕累托对比", "旧17组＋新3组；实心圆为可行解，叉号为不可行解。黑圈/虚线是联合候选中的二维前沿。")
pfp=plot("power_W",85,335,4.6,6.6,.4,"功耗—吞吐率")
pft=plot("peak_C",690,335,67,73,1,"峰温—吞吐率")
text(80,260,"灰色：上一轮矩形围栏方案     橙色：本轮拼图方案     两个二维前沿分别计算",13)
text(80,213,"本轮没有得到全面占优的方案：温度降低、吞吐率略升，同时线长和功耗增加。",14,bold=True)
text(80,178,"所有数值仍是相同物理代理模型的估算；填满可用区域是新增的布局偏好，不自动保证最高性能。",12)
footer("功耗与峰温均对应各方案自己的运行频率；虚线只连接已有可行点，不代表连续全局最优边界。")
finish("04_puzzle_pareto")
cv.save()
exe=Path.home()/".cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe"
subprocess.run([str(exe),"-r","144","-png",str(P),str(OUT/"rendered")],check=True)
for i,name in enumerate(pages,1):shutil.copyfile(OUT/f"rendered-{i}.png",OUT/f"{name}.png")
(OUT/"figure_manifest.json").write_text(json.dumps(dict(pages=pages,pdf=str(P),pareto_power=pfp,pareto_temperature=pft,
            all_cells_drawn=True,identical_netlist=True,old_run=old["winner"]["run"],new_run=m["winner"]["run"]),ensure_ascii=False,indent=2),encoding="utf-8")
print("Generated",P,"and",len(pages),"PNGs")
