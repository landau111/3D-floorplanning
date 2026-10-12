# 固定模块区域的 3D cell 级探索

**更新：非矩形拼图版已实现。** 见 [拼图版算法与数学原理](PUZZLE_METHOD.md)、[拼图布局PDF](output/pdf/puzzle_layouts.pdf)、[新增参数](puzzle_config.json)。以下内容保留原矩形围栏实验的复现口径；新实验在单独目录保存。

这是用户授权估算参数后运行的 **C-synthetic-exploration** 分支。它包含 16 个给定模块、29,400 个独立可移动的合成标准单元、2 个不可拆分 SRAM 硬宏、62,416 条合成两端网络。每个 cell 有自己的坐标；没有用一个模块矩形代替内部所有 cell 的位置。128 个固定点仅用于表示 SRAM 端口与分布式功率采样，**不计为标准单元**。

当前项目没有可用的退火候选文件，因此 A/B/C 都是新构造的假设布局，不是之前退火结果的复用。每组内部固定模块 tier 和矩形 fence，cell 可在 fence 内逐个移动。各组分层不同，便于日后用真实候选替换。没有 RTL/门级网表/Liberty/LEF/DEF/SDC/SAIF，因此本实验不能证明真实 C910 的最优策略，也不声称全局最优。

新增交付：[优化前后布局与帕累托图册](output/pdf/cell3d_layouts_and_pareto.pdf)、[图件索引](FIGURES.md)、[完整输入参数清单](PARAMETERS.md)、[机器可读输入全集](inputs_complete.json)。图中显示全部cell；原 `best_layout.svg` 仅为抽样概览。

图件复现（不重跑仿真）：`python cell3d/make_figures.py` → `python cell3d/render_figures.py`；参数清单复现：`python cell3d/input_inventory.py`。除NumPy外，绘图使用ReportLab，字体采用Windows微软雅黑；PNG优先由Poppler生成，缺少Poppler时可使用pypdfium2。

运行结果与方案排序见 [RESULTS.md](RESULTS.md)。参数见 [config.json](config.json)，完整可执行模型见 [simulate.py](simulate.py)。原有 `methodology.md` 与 `gem5-c910-baseline` 均保持原样。

## 运行

Python 3.12、NumPy 2.3.5；不依赖 GPU、PyTorch、EDA 商业软件或网络：

```powershell
python -m pip install -r cell3d/requirements.txt
python cell3d/simulate.py
python cell3d/write_summary.py
python cell3d/test_model.py
```

如果当前机器的 Python 不在 PATH，可使用本次已经验证的 bundled runtime：

```powershell
& 'C:\Users\yongxue\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' cell3d/simulate.py
& 'C:\Users\yongxue\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' cell3d/write_summary.py
& 'C:\Users\yongxue\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' cell3d/test_model.py
```

快速烟雾检查：`python cell3d/simulate.py --quick --output cell3d/smoke-results`。正式运行不要加 `--quick`。输出目录已存在时会覆盖同名生成文件。默认迭代：cell 160 步、routing 160 步，固定随机种子 20260925；正式结果另外对初选优胜方案做种子 17/41 的坐标扰动重启，重启方案也参加最终排名。

## 假设台账

| 项目 | 本次值 / 处理 | 来源 |
|---|---|---|
| 模块名 | 用户提供的 16 个名称，`tpe`、`mm` 等不擅自解释功能 | user-supplied |
| F2F pitch | 5 µm | user-supplied；互连类型为本次解释 |
| 局部 F2F 密度 | ≤20,000/mm² | user-supplied；按对齐的 0.1×0.1 mm 窗口执行 |
| 几何 pitch 上限 | (1000/5)²=40,000/mm²；与上述密度上限取较小值 | derived |
| 模型工艺、电压 | 假设 28 nm、0.8 V；并未加载该工艺 PDK | assumed |
| 层、面积 | 两层，每层 1.6×1.6 mm；tier 1 靠近散热器 | assumed |
| SRAM 宏 | `l2_b0` / `l2_b1` 各一个，分别固定于 tier 0/1，边长 0.76 mm | assumed；容量/宏版图未校准 |
| 标准单元 | 14 个逻辑模块各 2100 个，统一 8×4 µm；并非真实库尺寸分布或 C910 综合门数 | assumed |
| 模块 fence | 0.34×0.34 mm，单元面积利用率约 58.1% | assumed / derived |
| 基准动态 / 泄漏 | 2 GHz 下模块动态总和 7.59 W，60°C 泄漏 0.815 W；时钟开销包含于模块预算 | assumed |
| 线功耗 | 按长度、0.20 pF/mm、活动率 0.12、V²f 计算，再加到模块动态功耗 | assumed |
| 热环境 | 环境45°C，封装热阻3.5 K/W，上层散热；安全阈值95°C | assumed |
| RC、bond 延迟 | 线延迟 0.11L+0.04L² ns（L 为 mm），每个 bond 0.014 ns | assumed |
| 路由容量 | 3 个有效方向层×100 µm /0.5 µm=600 tracks/edge；宏区域乘0.45 | assumed |
| 功率/时序温度系数 | 泄漏 exp[0.012(T−60)]，逻辑 0.12%/K、连线0.2%/K | assumed |
| 原始 IPC | STREAM≈0.862142，MATMUL≈0.742577，来自原有 gem5 stats.json | measured in existing gem5 proxy run |
| 新 IPC | 解析 CPI 外推，没有重新运行 gem5，不是测量 | estimated |

若 `max_density_per_mm2` 原意是**标准单元**数量密度，则需改变约束对象并重跑；当前实现只对 F2F 信号连接执行该限制。当前不含电源、时钟 bond 预留，也不执行任意平移/任意形状窗口的滑动密度 DRC。5 µm 为合法 bond 网格 pitch，与 cell row/site 尺寸分别定义。

## 算法及与论文的对应

论文原作者的 [ASP-DAC 演讲稿](https://www.aspdac.com/aspdac2026/archive/pdf/3E-5.pdf) 与 [NVIDIA 论文入口](https://research.nvidia.com/labs/electronic-design-automation/papers/yichen_diffTier_aspdac26.pdf) 可供核对。已读取演讲稿：DRG-3D 用可微候选概率分配优化网络的拓扑、路径、走线层，并离散生成 tier guidance。**routing tier assignment 不等于 standard-cell tier assignment。**

本实现借鉴其“候选概率→期望资源需求→拥塞惩罚→梯度更新→离散验证”的思路。每个模块间两端网络使用 XY/YX 两种 L 路径×两种主干 tier，共4种选择，Softmax 松弛、手工解析梯度、Adam 更新。跨层端点需要1个 bond；同层网络借另一层路由需要2个 bond。宏区域折减路由容量。离散 argmax 后重新统计实际资源，不用期望拥塞冒充离散拥塞。

没有复现原文的多端 RSMT、3D DAG forest、分层 q/p/r 拓扑选择、商业 PRTG 集成、GPU 加速或 signoff 结果。新增 cell 移动与热优化属于本项目的扩展；主方法是梯度下降，不是模拟退火。

阶段一的无量纲目标为：

```
J = w_wire_timing × (0.45 × normalized_weighted_wirelength
                    + 1.5 × normalized_smooth_max_path_delay)
  + 30 × mean(relu(bin_density − 0.78)^2)
  + w_thermal × normalized_smooth_peak_temperature
  + w_spread × normalized_squared_power_map
```

`balanced/timing/thermal` 的三元权重依次为 `(1,.45,.40)/(1.8,.12,.15)/(.45,1.2,.50)`，在配置比较前固定。平滑 Manhattan 距离为 `sqrt(dx²+0.0004²)+sqrt(dy²+0.0004²)`。时序 smoothmax 温度为0.012 ns，热 smoothmax 温度为2°C。Adam β₁=.9、β₂=.999，坐标初始学习率0.006 mm，线性降到约20%。每步投影回模块 fence；返回连续目标最小点，再做逐单元 row/site 合法化。

阶段二优化路由 Softmax logits：`12×mean(route_overflow_ratio²)+5×mean(bond_overflow_ratio²)+criticality_weighted_bond_count`。路径长度相同的四个候选不重复加入常数线长项；电气差异通过 bond 数反映。Adam 学习率0.15。所有模块内网络使用固定同层 L 路由作为背景负载；模块间网络参与可微选择。

最后为每个 bond 分配窗口内独占的5 µm网格位置，并把相对端点的往返绕线距离加回功耗与时序。若超容量直接报不可行，不静默截断。

## 热—功耗—频率闭环

热模型是两层二维有限体积电阻网格。横向为绝热边界，tier 1 接散热边界，封装共模热阻另外加入。用离散 Laplacian 特征分解快速求 `ΔT=RθP`，模型内保功率且对固定功率线性。它并非 HotSpot，也未用实际材料堆栈校准。

cell 功率以双线性权重投到网格。泄漏按温度迭代至 node temperature 最大残差<1e−6°C，再根据最高温度与最差路径延迟，在0至2 GHz之间二分求同时满足 `Tmax≤95°C` 和 `delay_max×f≤1` 的最大频率。失稳/不收敛/无可用频率会报错。额外用32×32网格重算优胜方案，记录与16×16的差。

连续布局目标使用基准动态+60°C泄漏的固定功率近似，以保持优化廉价；最终评分才包含线电容、温度相关泄漏、合法 bond 绕线和频率反馈。这种阶段间代理偏差是结果必须离散重评的原因之一。

## 时序与 IPC 的准确口径

每条两端网络视为一个独立的“已寄存路径”代理：随机固定的0.24–0.35 ns逻辑延迟，模块间另加0.035 ns，再加温度相关线延迟与bond延迟。`WNS/TNS` 是这 **62,416 个合成路径代理** 的最差/总负裕量，不是对真实时序图的 STA，也不证明 setup/hold、时钟偏斜、重汇聚路径、缓冲插入和 DRC 收敛。

同时报告2 GHz标称频率下的 WNS/TNS/功耗/温度，及降频后可行运行点的功耗/温度/频率。降频后 WNS≈0 是按最差路径选频的结果，不应宣称优化已经满足2 GHz。

解析 IPC：

```
CPI(f) = CPI_gem5 × (1−m) + CPI_gem5 × m × f/2GHz
       + (L2_accesses / instructions) × 0.25 × (link_cycles−1)
link_cycles = max(1, ceil(p95_estimated_L2_link_delay_ns × f_GHz))
IPC = 1/CPI ; BIPS = IPC × f_GHz
```

`m=0.35/0.12` 分别是假设 STREAM/MATMUL CPI 中固定时间内存停顿占比，0.25为未被隐藏的 L2 链路停顿比例。原始缓存访问基础延迟包含在 gem5 CPI 中；只加相对一周期互连的增量，避免重复加整个L2访问时间。

因此频率降低时，固定ns的内存等待折合更少cycles，**IPC可能上升而吞吐率下降**。主排序按 STREAM/MATMUL BIPS 等权平均最大，其次按能耗/指令最小；必须先满足离散拥塞、bond密度、温度和时序条件。功率使用同一个代表性活动模型，并非逐 workload 活动标定；平均能耗也只是假设场景指标。所有 IPC 外推均未进行 gem5 R2 验证。

## 结果文件

- `results/manifest.json`：参数快照、种子、输入/源码SHA256、优胜方案、Pareto集合和验证。
- `results/metrics.csv`：三候选×初始/仅路由/三种cell目标，加两个重启结果。
- `results/sensitivity.csv`：每个候选的最佳可行方案，在功率±20%、RC±25%、封装热阻2.5/5 K/W及组合压力下重评；不是统计置信区间。
- `results/*_modules.csv`：16模块固定tier、区域、动态/泄漏假设，可直接查目前布局。
- `results/best_cells.csv`：逐cell坐标和tier，SRAM采样点有独立kind标签。
- `results/best_bonds.csv`、`best_route_guides.csv`：合法bond位置与网络主干tier/路径。
- `results/*.npz`：每个方案的cell、网络、温度场、离散路由选择。
- `results/*_trace.json`：目标收敛轨迹和合法化平均位移，支持检查连续与离散差异。

## 如何逐步变成真实 cell 流程

优先替换 `Design` 内 A/B/C 的 regions/tier 为已有退火候选；随后用综合网表和 LEF/DEF 替换合成cell、uniform尺寸和connections，保留SRAM硬宏及真实pin位置。再用Liberty/SDC与STA替换独立路径代理，用SAIF/VCD替换活动率，用提取RC/真实金属资源替换假设路由容量，用HotSpot/实际材料热参数校准热模型。最后把缓存/总线延迟周期回标到gem5重跑，才能把估算IPC升级为布局相关的仿真IPC。

本次敏感性检验没有覆盖未知网表、真实宏端口位置、实际工艺、时钟网络等结构性不确定性；它不能把代理模型的第一名提升为真实芯片的最优解。
