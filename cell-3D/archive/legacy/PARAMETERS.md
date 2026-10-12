# 实际输入参数全集

本清单对应已保存的17次实验。除用户给定模块名称、pitch=5µm、max_density_per_mm2=20000外，物理参数、网表、布局、目标权重都为本次假设；IPC基线来自原项目gem5结果。

参数分为：显式config、16模块功耗与几何、18组模块间连接、3组初始分层/坐标、代码固定算法参数、gem5读入字段、敏感性情景和数值验证设置。机器可读全集见 [inputs_complete.json](inputs_complete.json)。

`config.json` 并不包含全部输入：slot位置、网络随机生成规则、优化器权重、IPC停顿系数等固定在 `simulate.py`。本次将这些完整列出，未改变仿真代码或原结果。

## 1. 显式配置

共 42 个顶层标量/说明字段，加 `modules` 和 `connections` 两张表。node_nm_assumed仅用于口径标注，未加载28nm PDK。

| 键 | 实际值 | 含义 / 单位 | 来源 |
|---|---|---|---|
| `schema` | cell3d-estimate-v1 | 配置格式版本（元数据） | 估算/模型设置 |
| `track` | C-synthetic-exploration | 实验口径（元数据） | 估算/模型设置 |
| `provenance` | All physical parameters are assumptions except user-supplied bonding constraints. Not calibrated C910 physical design. | 物理参数来源声明（元数据） | 估算/模型设置 |
| `die_mm` | 1.6 | 每层die边长 / mm | 估算/模型设置 |
| `tiers` | 2 | 两层标记；求解器当前固定实现2层，不是任意层数求解器 | 估算/模型设置 |
| `node_nm_assumed` | 28 | 假设工艺节点 / nm；仅标签，不驱动PDK参数缩放 | 估算/模型设置 |
| `vdd_V` | 0.8 | 电源电压 / V；用于动态线功耗V² | 估算/模型设置 |
| `frequency_GHz` | 2.0 | 标称频率、动态功率参考频率、可行频率搜索上界 / GHz | 估算/模型设置 |
| `ambient_C` | 45.0 | 环境温度 / °C | 估算/模型设置 |
| `temperature_limit_C` | 95.0 | 最高温度可行性阈值 / °C | 估算/模型设置 |
| `package_R_K_W` | 3.5 | 封装共模热阻 / K/W | 估算/模型设置 |
| `lateral_G_W_K` | 0.008 | 相邻横向热节点导纳 / W/K | 估算/模型设置 |
| `intertier_G_W_K_at_16` | 0.012 | 16×16网格时层间每节点导纳 / W/K；加密后按(16/G)²缩放 | 估算/模型设置 |
| `top_sink_G_W_K_at_16` | 0.025 | 16×16网格时顶层散热节点导纳 / W/K；加密后按(16/G)²缩放 | 估算/模型设置 |
| `thermal_grid` | 16 | 每层热网格边长G | 估算/模型设置 |
| `routing_grid` | 16 | 每层路由网格边长G | 估算/模型设置 |
| `routing_tracks_per_edge` | 600 | 每条GCell边界的有效方向路由track数 | 估算/模型设置 |
| `routing_capacity_note` | Assumed 3 effective directional routing layers x 100um / 0.5um track pitch = 600 tracks per 0.1mm GCell edge before macro blockage. | 路由容量估算依据（说明） | 估算/模型设置 |
| `macro_routing_capacity_factor` | 0.45 | 宏区域路由容量乘数 | 估算/模型设置 |
| `pitch_um` | 5.0 | 层间信号连接pitch / µm；用户给定，约束对象由本次模型解释 | 用户给定，约束对象为本次解释 |
| `max_density_per_mm2` | 20000 | 层间信号连接局部数量密度 / mm⁻²；用户给定 | 用户给定，约束对象为本次解释 |
| `constraint_interpretation` | F2F signal bonds; fixed, aligned 0.1mm windows. Power/clock reserves not modeled. Not standard-cell count density. | pitch和density的约束对象、窗口及未建模预留（说明） | 估算/模型设置 |
| `cell_width_um` | 8.0 | 统一合成cell宽度、site宽 / µm | 估算/模型设置 |
| `cell_height_um` | 4.0 | 统一合成cell高度、row高 / µm | 估算/模型设置 |
| `cell_count_per_logic_module` | 2100 | 每个逻辑模块独立标准单元数 | 估算/模型设置 |
| `cell_geometry_note` | Uniform synthetic standard cells, each individually placed; no library mapping, clustering or claim to full C910 gate count. | 几何建模限制（说明） | 估算/模型设置 |
| `module_region_mm` | 0.34 | 逻辑模块可移动区域的正方形边长 / mm | 估算/模型设置 |
| `macro_side_mm` | 0.76 | 每个SRAM硬宏边长 / mm | 估算/模型设置 |
| `wire_C_pF_per_mm` | 0.2 | 单位长度线电容 / pF/mm | 估算/模型设置 |
| `wire_activity` | 0.12 | 线动态功耗活动率 | 估算/模型设置 |
| `wire_delay_ns_per_mm` | 0.11 | 线延迟L项系数 / ns/mm | 估算/模型设置 |
| `wire_delay_ns_per_mm2` | 0.04 | 线延迟L²项系数 / ns/mm² | 估算/模型设置 |
| `bond_C_pF` | 0.004 | 每个层间信号连接电容 / pF | 估算/模型设置 |
| `bond_delay_ns` | 0.014 | 每个层间信号连接延迟 / ns | 估算/模型设置 |
| `leakage_alpha_per_K` | 0.012 | 泄漏指数温度系数 / K⁻¹ | 估算/模型设置 |
| `leakage_reference_C` | 60.0 | 泄漏与延迟温度系数参考点 / °C | 估算/模型设置 |
| `logic_delay_alpha_per_K` | 0.0012 | 逻辑延迟线性温度系数 / K⁻¹ | 估算/模型设置 |
| `wire_delay_alpha_per_K` | 0.002 | 线延迟线性温度系数 / K⁻¹ | 估算/模型设置 |
| `density_target` | 0.78 | cell面积网格密度软约束目标，非F2F数量密度上限 | 估算/模型设置 |
| `placement_steps` | 160 | cell Adam迭代步数 | 估算/模型设置 |
| `routing_steps` | 160 | routing Adam迭代步数 | 估算/模型设置 |
| `seed` | 20260925 | 合成布局、活动、网表与逻辑延迟随机种子 | 估算/模型设置 |

## 2. 16模块与功耗预算

动态功率参考2 GHz；泄漏参考60°C。14逻辑模块各2100个8×4µm合成cell，2个SRAM宏固定；模块总动态7.59W、参考泄漏0.815W，连线功耗另行计算。

| 模块 | 类型 | 标准单元数 | 动态 W | 60°C泄漏 W |
|---|---|---:|---:|---:|
| l2_b0 | sram_macro | 0（64个固定采样点） | 0.55 | 0.1 |
| l2_b1 | sram_macro | 0（64个固定采样点） | 0.55 | 0.1 |
| if_pp | logic | 2100 | 0.38 | 0.035 |
| if_ctl | logic | 2100 | 0.2 | 0.02 |
| l2_ctl | logic | 2100 | 0.3 | 0.03 |
| tpe | logic | 2100 | 0.18 | 0.02 |
| ls | logic | 2100 | 0.8 | 0.07 |
| mm | logic | 2100 | 0.24 | 0.025 |
| id | logic | 2100 | 0.32 | 0.03 |
| rn | logic | 2100 | 0.34 | 0.035 |
| is_int | logic | 2100 | 0.54 | 0.045 |
| ix | logic | 2100 | 0.72 | 0.065 |
| vec_vx | logic | 2100 | 1.05 | 0.09 |
| is_int_fwd | logic | 2100 | 0.32 | 0.03 |
| is_int_rf | logic | 2100 | 0.55 | 0.07 |
| vec_is_vec | logic | 2100 | 0.55 | 0.05 |

## 3. 模块间网络数量

每项是合成两端net数量，不是RTL测得bus宽。模块内每cell另接偏移1和7的环形ID邻居，合计58800条；以下3616条模块间网络，总计62416条。

| 源模块 | 目的模块 | 网络数量 |
|---|---|---:|
| if_pp | if_ctl | 96 |
| if_ctl | id | 128 |
| id | rn | 192 |
| rn | is_int | 192 |
| is_int | ix | 256 |
| ix | is_int_fwd | 256 |
| is_int_fwd | is_int_rf | 256 |
| is_int_rf | is_int | 256 |
| rn | vec_is_vec | 192 |
| vec_is_vec | vec_vx | 384 |
| ix | ls | 128 |
| ls | mm | 128 |
| ls | l2_ctl | 256 |
| l2_ctl | l2_b0 | 256 |
| l2_ctl | l2_b1 | 256 |
| mm | tpe | 64 |
| tpe | if_ctl | 64 |
| vec_vx | ls | 256 |

## 4. 三组候选的完整分层与位置

所有坐标为模块左下角，单位mm；tier0是下层、tier1是散热侧。每组优化时分层/模块fence固定，只优化cell和走线。图采用A方案的初始与最终获选结果。

### A_split

| 模块 | tier | x | y | 宽 | 高 |
|---|---:|---:|---:|---:|---:|
| l2_b0 | 0 | 0.02 | 0.82 | 0.76 | 0.76 |
| l2_b1 | 1 | 0.02 | 0.82 | 0.76 | 0.76 |
| if_pp | 0 | 0.03 | 0.03 | 0.34 | 0.34 |
| if_ctl | 0 | 0.43 | 0.03 | 0.34 | 0.34 |
| l2_ctl | 1 | 0.03 | 0.03 | 0.34 | 0.34 |
| tpe | 1 | 0.43 | 0.03 | 0.34 | 0.34 |
| ls | 0 | 0.83 | 0.43 | 0.34 | 0.34 |
| mm | 1 | 0.03 | 0.43 | 0.34 | 0.34 |
| id | 0 | 0.03 | 0.43 | 0.34 | 0.34 |
| rn | 0 | 0.43 | 0.43 | 0.34 | 0.34 |
| is_int | 0 | 0.83 | 0.03 | 0.34 | 0.34 |
| ix | 0 | 1.23 | 0.03 | 0.34 | 0.34 |
| vec_vx | 1 | 0.43 | 0.43 | 0.34 | 0.34 |
| is_int_fwd | 1 | 0.83 | 0.03 | 0.34 | 0.34 |
| is_int_rf | 1 | 1.23 | 0.03 | 0.34 | 0.34 |
| vec_is_vec | 1 | 0.83 | 0.43 | 0.34 | 0.34 |

### B_critical_local

| 模块 | tier | x | y | 宽 | 高 |
|---|---:|---:|---:|---:|---:|
| l2_b0 | 0 | 0.02 | 0.82 | 0.76 | 0.76 |
| l2_b1 | 1 | 0.02 | 0.82 | 0.76 | 0.76 |
| if_pp | 1 | 0.03 | 0.03 | 0.34 | 0.34 |
| if_ctl | 1 | 0.43 | 0.03 | 0.34 | 0.34 |
| l2_ctl | 1 | 0.83 | 0.03 | 0.34 | 0.34 |
| tpe | 1 | 1.23 | 0.03 | 0.34 | 0.34 |
| ls | 0 | 0.43 | 0.43 | 0.34 | 0.34 |
| mm | 1 | 1.23 | 0.43 | 0.34 | 0.34 |
| id | 0 | 0.03 | 0.03 | 0.34 | 0.34 |
| rn | 0 | 0.43 | 0.03 | 0.34 | 0.34 |
| is_int | 0 | 0.83 | 0.03 | 0.34 | 0.34 |
| ix | 0 | 1.23 | 0.03 | 0.34 | 0.34 |
| vec_vx | 1 | 0.43 | 0.43 | 0.34 | 0.34 |
| is_int_fwd | 0 | 1.23 | 0.43 | 0.34 | 0.34 |
| is_int_rf | 0 | 0.83 | 0.43 | 0.34 | 0.34 |
| vec_is_vec | 1 | 0.83 | 0.43 | 0.34 | 0.34 |

### C_hot_top

| 模块 | tier | x | y | 宽 | 高 |
|---|---:|---:|---:|---:|---:|
| l2_b0 | 0 | 0.02 | 0.82 | 0.76 | 0.76 |
| l2_b1 | 1 | 0.02 | 0.82 | 0.76 | 0.76 |
| if_pp | 1 | 0.83 | 0.43 | 0.34 | 0.34 |
| if_ctl | 1 | 0.03 | 0.43 | 0.34 | 0.34 |
| l2_ctl | 0 | 1.23 | 0.03 | 0.34 | 0.34 |
| tpe | 0 | 0.83 | 0.03 | 0.34 | 0.34 |
| ls | 1 | 0.83 | 0.03 | 0.34 | 0.34 |
| mm | 0 | 0.43 | 0.03 | 0.34 | 0.34 |
| id | 1 | 0.43 | 0.43 | 0.34 | 0.34 |
| rn | 1 | 0.03 | 0.03 | 0.34 | 0.34 |
| is_int | 1 | 0.43 | 0.03 | 0.34 | 0.34 |
| ix | 1 | 1.23 | 0.03 | 0.34 | 0.34 |
| vec_vx | 0 | 0.03 | 0.03 | 0.34 | 0.34 |
| is_int_fwd | 0 | 0.43 | 0.43 | 0.34 | 0.34 |
| is_int_rf | 0 | 0.03 | 0.43 | 0.34 | 0.34 |
| vec_is_vec | 0 | 0.83 | 0.43 | 0.34 | 0.34 |

## 5. 代码固定的算法与评估参数

这些参数目前不是CLI/config可直接切换项。修改固定参数需要改代码并重新运行，不能只改说明文件。

| 类别 | 参数 | 实际值 | 作用 |
|---|---|---|---|
| 布局几何 | `slot_grid` | 4×4; slot_pitch=0.4 mm | 宏占左上2×2格，其余12格可放逻辑模块；每层用7格 |
| 布局几何 | `logic_slot_margin` | 0.03 mm | 逻辑区域左下角=(slot_x×0.4+0.03,slot_y×0.4+0.03) |
| 布局几何 | `macro_origin` | (0.02,0.82) mm | 两层各一个固定宏；区域到(0.78,1.58) mm |
| 布局几何 | `candidate_slot_orders` | {"A_split": [0, 1, 4, 5, 2, 3, 6], "B_critical_local": [0, 1, 2, 3, 7, 6, 5], "C_hot_top": [3, 2, 1, 0, 5, 4, 6]} | slot按y优先、再x遍历，排除左上2×2 |
| 网表与功率 | `macro_port_power_samples` | 8×8=64 points/macro; inset=0.01 mm | 只作固定端口/功率采样，不是可移动SRAM bit cells |
| 网表与功率 | `initial_cell_sampling` | unique random legal row/sites | 每模块从42×85=3570个合法site中无放回取2100个 |
| 网表与功率 | `cell_activity_distribution` | Uniform(0.65,1.35), normalized per module | 只决定模块动态功率如何分到cell，模块总和保持给定预算 |
| 网表与功率 | `leakage_distribution` | uniform per module | 每cell泄漏等于模块泄漏/节点数 |
| 网表与功率 | `local_net_offsets` | 1,7; circular IDs | 每个逻辑cell连接ID偏移1和7的两个cell；共58800条模块内两端网络 |
| 网表与功率 | `external_net_endpoints` | independent random choice with replacement | 按config.connections指定数量生成模块间网络，合计3616条 |
| 时序代理 | `base_logic_delay` | Uniform(0.24,0.35) ns | 每条两端网络是独立的已寄存路径代理，不是完整STA图 |
| 时序代理 | `external_logic_extra` | 0.035 ns | 模块间网络额外固定逻辑延迟 |
| 时序代理 | `criticality` | 1+2×I(logic_ns>0.34 ns) | 用于线长和bond目标的固定关键性权重，取1或3 |
| cell优化 | `profiles` | {"balanced": [1.0, 0.45, 0.4], "timing": [1.8, 0.12, 0.15], "thermal": [0.45, 1.2, 0.5]} | 三元组=(wire_timing,thermal,power_spread) |
| cell优化 | `inner_weights` | wire=0.45; smooth_timing=1.5; density=30 | J=w0(0.45WL+1.5Timing)+30mean(overflow²)+w1Heat+w2Spread |
| cell优化 | `normalization` | wire=0.25 mm; timing=0.5 ns; temperature=40 K | 把不同项变成无量纲分数；power spread=bin_count×sum(Pbin²)/Ptotal² |
| cell优化 | `wire_smoothing` | epsilon=0.0004 mm | sqrt(dx²+epsilon²)+sqrt(dy²+epsilon²) |
| cell优化 | `smoothmax_temperatures` | timing=0.012 ns; thermal=2°C | log-sum-exp平滑峰值；不是物理温度设定 |
| cell优化 | `adam` | beta1=0.9; beta2=0.999; epsilon=1e-9 | 含偏差修正 |
| cell优化 | `coordinate_learning_rate` | 0.006×(0.20+0.80×(1−i/steps)) mm | 每步投影回固定模块fence；取最小连续目标点后合法化 |
| cell优化 | `restart_seeds` | 17,41 | 对初选优胜方案追加独立坐标扰动优化，两者也参与最后排名 |
| cell优化 | `restart_perturbation` | Normal(0,0.003 mm) | 添加到初始坐标后投影回模块区域 |
| cell优化 | `legalizer` | y,x lexicographic order; growing square ring | 在模块内搜索空闲site，选当前搜索窗内欧氏距离最近位置；不是全局最优合法化 |
| 路由优化 | `candidate_space` | 2 L paths (XY,YX) × 2 trunk tiers=4 | 模块间网参与优化；模块内网固定同层XY背景路由 |
| 路由优化 | `softmax` | temperature=1 | logits归一化；最终argmax离散 |
| 路由优化 | `initial_logits` | baseline_choice=0.1; other=0 | 初始偏好源端点tier的XY路径 |
| 路由优化 | `baseline_route` | source endpoint tier; XY | 用于优化前参考 |
| 路由优化 | `loss_weights` | route_overflow=12; bond_overflow=5 | mean(max(demand/capacity−1,0)²) |
| 路由优化 | `bond_cost` | (0.08+0.04×criticality)/guided_net_count | 期望bond数乘关键性相关系数 |
| 路由优化 | `adam_learning_rate` | 0.15 | beta1=.9,beta2=.999,epsilon=1e−9 |
| 路由优化 | `macro_capacity_region` | x∈[0.02,0.78], y∈[0.82,1.58] mm | 硬编码宏覆盖检查；折减系数从config读取 |
| bond合法化 | `window` | aligned die_mm/routing_grid=0.1 mm | 只检查对齐窗口；不实现滑动窗口DRC |
| bond合法化 | `sites` | 20×20=400 pitch sites/window; density capacity=200 | 坐标偏移半pitch；取min(20000,40000)×0.01；同一位置只容纳1个bond |
| bond合法化 | `site_assignment` | nearest available site in endpoint bin | 按网络顺序分配；超容量报错 |
| bond合法化 | `wire_detour_factor` | 2 | 合法bond到端点的Manhattan距离×2加入对应网络长度 |
| 热与求解 | `boundary` | adiabatic sides; tier1 to sink; package common mode | 两层有限体积RC模型，不是HotSpot材料堆栈 |
| 热与求解 | `power_deposition` | bilinear to cell-centered thermal grid | 热节点坐标夹在[0,G−1−1e−9]，边界外导数为0 |
| 热与求解 | `leakage_fixed_point` | max_iterations=150; tolerance=1e−6°C; damping=0.5 | 初值60°C；残差为最大cell温度更新差 |
| 热与求解 | `runaway_threshold` | 250°C | 超过阈值报热失稳，不返回伪造结果 |
| 热与求解 | `frequency_search` | 26 bisections; bracket=[0,2] GHz; usable minimum=0.1 GHz | 2GHz上限实际取config.frequency_GHz；最低可用频率以下报错 |
| 热与求解 | `thermal_refinement` | G=32 | 只对最终优胜方案加密重算验证，不重新优化cell |
| IPC外推 | `memory_CPI_fraction` | {"stream": 0.35, "matmul": 0.12} | 固定ns内存停顿在基准CPI中的假设占比 |
| IPC外推 | `unhidden_L2_fraction` | 0.25 | L2访问/指令×0.25×额外互连cycles |
| IPC外推 | `link_delay_statistic` | p95(delay−base_logic_ns) | 仅涉及l2_b0/l2_b1/l2_ctl的网；包含温度相关逻辑附加延迟 |
| IPC外推 | `link_cycles` | max(1,ceil(link_ns×f_GHz)) | 以1cycle为已有CPI内含的互连基线；本次结果均为1cycle |
| 选择与探索 | `workload_weights` | {"stream": 0.5, "matmul": 0.5} | 最大化等权平均BIPS，平局时最小化能耗/指令 |
| 选择与探索 | `feasibility` | route overflow=0; bond density≤capacity; Tmax≤95°C; delay_max×f≤1 | 本模型离散可行，不代表详细布线/hold/PDN/DRC签核 |
| 选择与探索 | `pareto_objectives` | min power_W; min peak_C; max mean_bips | 只比较离散可行方案；图上另外独立计算两个二维前沿 |
| 选择与探索 | `sensitivity_scenarios` | {"nominal": {}, "power_minus20": {"power_scale": 0.8}, "power_plus20": {"power_scale": 1.2}, "rc_minus25": {"rc_scale": 0.75}, "rc_plus25": {"rc_scale": 1.25}, "cooling_good": {"package_R": 2.5}, "cooling_poor": {"package_R": 5.0}, "combined_stress": {"power_scale": 1.2, "rc_scale": 1.25, "package_R": 5.0}} | 固定优化后布局，扰动功率、线/bond延迟RC乘数与封装热阻；不是真实统计置信区间 |
| 数值验证 | `gradient_check` | placement seed81;20 cells×2coords;step1e−7 mm; routing10 logits;step1e−5 | 相对误差门限1%；仅验证，不属于芯片技术输入 |
| 数值验证 | `thermal_grid_acceptance` | peak delta<0.5°C | 验证脚本断言阈值 |

## 6. 从已有gem5结果读入的数值

来源：`../gem5-c910-baseline/results/stats.json`。模拟器只使用CPI、指令数与L2 access计算外推，IPC用于展示基线。没有把ROB、发射宽度、完整cache配置等再次输入cell优化器，也没有重新运行gem5。

| 工作负载 | 基准IPC | 基准CPI | 指令数 | L2 access |
|---|---:|---:|---:|---:|
| stream | 0.862142007 | 1.159901724 | 7590431 | 370329 |
| matmul | 0.742576688 | 1.346662259 | 3914594 | 5533 |

原始输入SHA256：`6ed6d8051a3c2fe3421f3c7c300815e25d5cf12c31f1a2ef89362260666a6165`。

## 7. 当前没有输入的真实工程资料

未输入实际门级网表、Liberty标准单元库、LEF/DEF、SDC、SAIF/VCD、寄生RC提取、真实SRAM端口、材料堆栈、时钟树、电源/时钟bond预留、IR-drop/EM约束或详细路由规则。因此所有新功耗/温度/时序/IPC属于参数化估算。

## 8. 修改参数时的依赖

几何生成器含0.4mm slot与固定宏位置，不能只改die_mm就认为布局会自动缩放。路由每边600tracks是0.1mm GCell的假设，修改routing_grid时需同步重算容量。当前只支持两层和统一cell尺寸；工艺node_nm_assumed只改标签，不改变RC或面积。所有变化均须重跑并重新验证。
