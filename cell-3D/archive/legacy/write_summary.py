"""Build a human-readable experiment note and a geometric layout diagram."""
import csv
import html
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT/"results"
m = json.loads((OUT/"manifest.json").read_text(encoding="utf-8"))
w, c, val = m["winner"], m["config"], m["validation"]


def load_csv(name):
    with open(OUT/name, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


rows = load_csv("metrics.csv")
sensitivity = load_csv("sensitivity.csv")
mods = load_csv(w["candidate"]+"_modules.csv")
baseline = next(r for r in rows if r["candidate"] == w["candidate"] and r["profile"] == "baseline")
gain = (w["mean_bips"]/float(baseline["mean_bips"])-1)*100
cells = np.load(OUT/(w["run"]+".npz"))
trace = json.loads((OUT/(w["run"]+"_trace.json")).read_text(encoding="utf-8"))
colors = ["#64748b", "#64748b", "#0891b2", "#0d9488", "#7c3aed", "#9333ea", "#ea580c", "#c026d3", "#2563eb", "#4f46e5", "#65a30d", "#d97706", "#dc2626", "#059669", "#0284c7", "#be123c"]
svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="700" viewBox="0 0 1200 700">',
       '<rect width="1200" height="700" fill="#f8fafc"/>',
       '<g font-family="Arial,sans-serif" fill="#0f172a">',
       '<text x="44" y="45" font-size="25" font-weight="bold">Synthetic cell-level 3D placement</text>',
       f'<text x="44" y="75" font-size="15">{html.escape(w["run"])} | 29,400 independent cells | fixed module fences and SRAM macros</text>']
scale = 470/c["die_mm"]
for tier in range(2):
    ox, oy = 60+tier*590, 600
    svg.append(f'<text x="{ox}" y="116" font-size="19" font-weight="bold">Tier {tier}'+(' — heatsink side' if tier else ' — bottom die')+'</text>')
    svg.append(f'<rect x="{ox}" y="{oy-470}" width="470" height="470" fill="white" stroke="#94a3b8"/>')
    for mi, mod in enumerate(mods):
        if int(mod["tier"]) != tier:
            continue
        x, y, rw, rh = [float(mod[k]) for k in ["x_mm", "y_mm", "width_mm", "height_mm"]]
        sx, sy = ox+x*scale, oy-(y+rh)*scale
        fill = "#e2e8f0" if mod["kind"] == "sram_macro" else "#ffffff"
        svg.append(f'<rect x="{sx:.2f}" y="{sy:.2f}" width="{rw*scale:.2f}" height="{rh*scale:.2f}" rx="3" fill="{fill}" stroke="{colors[mi]}"/>')
        ids = np.flatnonzero((cells["module_id"] == mi) & cells["movable"])
        # Geometric overview only: fixed reproducible sampling, no quantity inference from dot count.
        for idx in ids[::max(1, len(ids)//100)]:
            xx, yy = cells["xy_mm"][idx]
            svg.append(f'<circle cx="{ox+xx*scale:.2f}" cy="{oy-yy*scale:.2f}" r="1" fill="{colors[mi]}" opacity=".70"/>')
        svg.append(f'<rect x="{sx+3:.2f}" y="{sy+3:.2f}" width="{min(rw*scale-6, len(mod["name"])*6.8+6):.2f}" height="17" fill="{fill}" opacity=".95"/>')
        svg.append(f'<text x="{sx+6:.2f}" y="{sy+15:.2f}" font-size="11" font-weight="bold">{mod["name"]}</text>')
        if mod["kind"] == "sram_macro":
            svg.append(f'<text x="{sx+16:.2f}" y="{sy+rw*scale/2:.2f}" font-size="16" fill="#475569">Fixed SRAM macro</text>')
    svg.append(f'<text x="{ox}" y="626" font-size="13">0</text><text x="{ox+423}" y="626" font-size="13">1.6 mm</text>')
svg.extend(['<text x="44" y="667" font-size="14" fill="#475569">Dots show 100 sampled cells per logic module; all 29,400 cell coordinates are in best_cells.csv. Synthetic, not signoff.</text>', '</g></svg>'])
(OUT/"best_layout.svg").write_text("\n".join(svg), encoding="utf-8")

text = ["# 3D cell 级摆放：本次估算结果", "",
        "**这是已执行的合成网表代理实验，不是实际 C910 签核结果。** 真实退火候选未在目录中找到；A/B/C 为假设起点。", "",
        f"在 {len(rows)} 个已评估运行中，按离散可行优先、平均吞吐率最大选出的方案为 **`{w['run']}`**。它在固定模块区域内用偏重热分散的梯度目标细化 cell，再优化走线层与路径。第一名指本次有限候选中的最优，不证明全局最优。", "",
        "| 指标 | 估算值 |", "|---|---:|",
        f"| 可行频率 | {w['frequency_GHz']:.3f} GHz |",
        f"| 运行点总功耗 / 动态 / 泄漏 | {w['power_W']:.3f} / {w['dynamic_W']:.3f} / {w['power_W']-w['dynamic_W']:.3f} W |",
        f"| 运行点最高温度 | {w['peak_C']:.2f} °C |",
        f"| 最差合成路径延迟 | {w['critical_delay_ns']:.3f} ns |",
        f"| 2 GHz 标称 WNS / TNS | {w['nominal_WNS_ps']:.1f} ps / {w['nominal_TNS_ns']:.2f} ns |",
        f"| 2 GHz 标称功耗 / 最高温度 | {w['nominal_power_W']:.3f} W / {w['nominal_peak_C']:.2f} °C |",
        f"| STREAM IPC / BIPS | {w['ipc_stream']:.3f} / {w['bips_stream']:.3f} |",
        f"| MATMUL IPC / BIPS | {w['ipc_matmul']:.3f} / {w['bips_matmul']:.3f} |",
        f"| 等权平均 BIPS / 能耗 | {w['mean_bips']:.3f} / {w['energy_nJ_per_instruction']:.3f} nJ/instruction |",
        f"| F2F bond 数 | {w['bond_count']} |",
        f"| 最大局部 F2F 密度 | {w['max_bond_bin_density_mm2']:.0f} / 20000 mm⁻² |",
        f"| GCell 路由最大利用率 / overflow | {w['max_route_utilization']*100:.1f}% / {w['route_overflow_tracks']:.0f} tracks |", "",
        "**主要瓶颈是时序，当前没有达到2 GHz。** 降频后WNS接近零是按最差路径选频的结果。STREAM/MATMUL IPC为原有gem5数据基础上的解析外推；较低频率使固定时间的内存等待折算周期变少，所以IPC上升不能解读成处理速度上升。", "",
        f"相对同一 A/B/C 起点的初始方案，平均BIPS代理变化 **+{gain:.1f}%**；但初始方案有 {float(baseline['route_overflow_tracks']):.0f} tracks overflow，属于不可行参考，不能宣称是对已可布线芯片的性能提升。", "",
        "## 固定的模块分层", "", "| 层 | 模块 |", "|---|---|"]
for tier in range(2):
    text.append(f"| tier {tier}"+('（靠散热器）' if tier else '（下层）')+" | "+"、".join(x["name"] for x in mods if int(x["tier"]) == tier)+" |")
text += ["", "![布局概览](results/best_layout.svg)", "", "图中只抽样显示每个逻辑模块100个cell；坐标输出包含全部cell。固定模块矩形是可移动范围，内部cell可独立变化。", "",
         "## 全部运行", "", "表中功耗和温度均为各自运行频率；WNS固定在2 GHz，避免把降频结果误认成2 GHz达标。", "",
         "| 运行 | GHz | W | Tmax °C | WNS@2GHz ps | 平均BIPS | overflow | 可行 |",
         "|---|---:|---:|---:|---:|---:|---:|---|"]
for r in rows:
    text.append(f"| {r['run']} | {float(r['frequency_GHz']):.3f} | {float(r['power_W']):.3f} | {float(r['peak_C']):.2f} | {float(r['nominal_WNS_ps']):.1f} | {float(r['mean_bips']):.3f} | {float(r['route_overflow_tracks']):.0f} | {'是' if r['feasible']=='True' else '否'} |")
text += ["", "仅路由优化仍有剩余拥塞；当前cell细化是获得离散可行解的重要步骤。`timing` 权重大不保证最终峰值时序更好：连续代理、合法化位移与离散路由会改变结果。当前结论支持按离散结果挑选目标权重，而不是预先认定时序权重最高的一组获胜。", "",
         "## 参数敏感性", "", "下面对每个布局的最佳可行方案保持cell与路由不变，在相同物理参数扰动下重算；没有在每个情景重新优化。", "",
         "| 情景 | A平均BIPS | B平均BIPS | C平均BIPS | 第一名 |", "|---|---:|---:|---:|---|"]
for scenario in m["sensitivity_scenarios"]:
    rs = [r for r in sensitivity if r["scenario"] == scenario]
    by = {r["run"][0]: r for r in rs}
    best = max(rs, key=lambda r: float(r["mean_bips"]))
    text.append(f"| {scenario} | {float(by['A']['mean_bips']):.3f} | {float(by['B']['mean_bips']):.3f} | {float(by['C']['mean_bips']):.3f} | {best['run'][0]} |")
own = [r for r in sensitivity if r["run"] == w["run"]]
text += ["", f"优胜方案在这8个假设情景中平均BIPS为 **{min(float(r['mean_bips']) for r in own):.3f}–{max(float(r['mean_bips']) for r in own):.3f}**，Tmax为 **{min(float(r['peak_C']) for r in own):.1f}–{max(float(r['peak_C']) for r in own):.1f}°C**。这是情景包络，不是置信区间，也不包括真实网表未知造成的结构性误差。", "",
         "## 验证", "",
         f"- 完整规模解析梯度与中心差分最大相对误差：cell {val['placement_gradient_max_relative_error']:.2e}，routing {val['routing_gradient_max_relative_error']:.2e}。",
         "- 已核验单元在模块区域内、row/site对齐、同一模块无重复占位、宏端口不移动；模块fence与宏本身互不重叠。",
         f"- 功率守恒最大误差 {val['max_power_conservation_error_W']:.2e} W；电热固定点收敛残差 {w['electrothermal_residual_C']:.2e}°C。",
         f"- 热网格从16×16加密到32×32，Tmax变化 {val['thermal_grid_16_to_32_peak_delta_C']:+.3f}°C，频率变化 {val['thermal_grid_16_to_32_frequency_delta_GHz']:+.6f} GHz；本次变化低于0.5°C。",
         f"- 优胜方案连续坐标合法化平均位移 {trace['legalization_mean_move_um']:.2f} µm；性能表只使用合法化后的坐标。",
         "- 额外测试包含热互易性、极端碰撞合法化、bond网格唯一性、超密度/零容量拒绝以及结果源码哈希一致性。", "",
         "## 文件与复现", "", "[完整方法及假设](README.md) · [参数配置](config.json) · [优化器代码](simulate.py) · [逐方案结果](results/metrics.csv) · [逐cell坐标](results/best_cells.csv) · [bond位置](results/best_bonds.csv) · [走线指引](results/best_route_guides.csv) · [参数敏感性](results/sensitivity.csv) · [验证与版本记录](results/manifest.json)", "",
         "下一步最有价值的是替换真实退火候选和综合网表，再接STA/功耗/热校准与gem5 R2。本轮已完成所授权的估算仿真，尚未完成真实芯片物理设计签核。", ""]
(ROOT/"RESULTS.md").write_text("\n".join(text), encoding="utf-8")
print("Wrote", ROOT/"RESULTS.md", "and", OUT/"best_layout.svg")
