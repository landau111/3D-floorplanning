# 模块级双 die 折叠布局探索器

读取脱敏的模块面积、功耗、连接数和布局约束，探索上下层分配、模块位置及宽高比。
**当前温度只由真实 HotSpot 计算。旧的自写导热求解器、Gaussian 热点评分及其配置参数已删除。**

安装、运行、调参及排错参见根目录的 [操作手册](../操作手册.md)。本文件说明模型与算法。

## 运行

在项目根目录运行。CentOS/Linux 需要 Python 3.6+、GNU make 和 GCC；不需要 pip、NumPy、Matplotlib、SuperLU 或 BLAS。
HotSpot C 源码已经包含在 `third_party/HotSpot`，保留上游许可；布局搜索本身使用 Python 标准库。

```bash
make hotspot       # 首次编译 HotSpot；GNU99 兼容较旧 GCC
make test-hotspot  # 行为测试 + 真实 HotSpot 一致性测试
make quick         # 6组权重，每组3轮，500次几何扰动，1次重启
make explore       # 使用 YAML 的40轮，每轮1000次几何扰动，2次重启
make optimize      # 使用配置权重，只选出一个方案，同样调用 HotSpot
```

`make quick/explore/optimize` 自动先检查/编译 HotSpot。不支持仅靠 Python 计算温度。
缺失 HotSpot、运行失败、超时或返回异常网格时会明确报错，不能退回旧模型。

```bash
make explore ARGS="--config folding_dse/folding_dse_annealing_cfg.yaml --output folding_dse/my_run --steps 2000 --restarts 2 --thermal-rounds 40"
make explore ARGS="--hotspot-exe /absolute/path/hotspot --profiles balanced,thermal,constraint"
# 没有 make 时，先完成 HotSpot 编译，然后：
python3 folding_dse/run.py explore
```

Windows 使用 `./run.cmd quick` 或 `./run.cmd explore`。提供 `--hotspot-exe` 时运行本机 HotSpot；否则自动使用已有非 Docker 的 WSL 发行版，用其中的 GCC/make/Python3 编译和运行。可设置环境变量 `FOLDING_DSE_WSL_DISTRO` 指定发行版。
双击 `run.cmd` 执行正常探索，结束后保留窗口。默认输出在 `folding_dse/local_results` / `quick_results` / `single_results`。
默认目录已有结果时自动新建时间戳目录；显式 `--output` 请使用新目录，防止混合不同配置的结果。

## 本次配置及 YAML 样式

默认输入为 `folding_dse_annealing_cfg.yaml`，根据 2026-10-08 的附件整理，保留原来的注释分段、模块顺序、`模块名: [参数]` 和 `- 项目` 列表写法。
修正了列表字段的缩进、裸露的说明文字、`if_ctrl` → 已定义的 `if_ctl`，并删除两条完全重复的配对约束。
注释中的 Top 要求写为明确的 `layer: top`。空白的层结构部分补了可替换的估计值。
这里使用内置的严格 YAML 子集解析器，支持嵌套映射、列表映射及 `[ ]` / `{ }`；无需安装 PyYAML。
不支持 YAML 标签、锚点或多行字符串。未知字段、重复键、未知模块及相互矛盾的 HBT 密度参数会报错。

新增参数均进入评价：

| 参数 | 当前使用方式 |
| --- | --- |
| `layout_constrains` | 同层、指定 Top 层及中心曼哈顿距离超限的软惩罚，逐条报告 |
| `power_w` | 新功耗合计 **0.845 W**，作为 HotSpot 的发热输入 |
| `ambient_c`、`grid_rows/cols` | 26.85℃，每个物理层 64×64 网格 |
| `hbt` | 5 µm pitch、20,000/mm² 密度上限，扣除 20% 预留 |
| `timing` | 单条跨层连接 100 ps，时钟周期 333 ps，占周期约 0.3003 |
| `critical_modules`、`net_weights` | 按关键—关键、关键—其他、其他—其他分类加权；附件三类权重均为1，按原值执行 |
| `rc_temp_alpha/ref_temp` | 使用 HotSpot 模块温度修正 RC 排序代价，系数0.0039/K，参考27℃ |
| `hbt_vert_um` | 跨层连接的几何长度加10 µm；不把它当作 HB 热界面的厚度 |
| `anneal.iters` | 40次外层热反馈，每次先用几何退火生成候选，再实际调用 HotSpot |
| `shape_aspects` | 软模块可选宽高比，面积保持不变，可自行扩展搜索形状 |

`config.yaml` 是解析器依赖的内部默认值与早期测试数据来源；日常修改 `folding_dse_annealing_cfg.yaml`。过期的 `config_enlarged.yaml` 已移除。

## 布局约束与冲突

硬约束：固定的两个 L2 宏在 bottom；所有模块位于 die 内，同层不重叠，间距至少0.008 mm；每层面积 ≤ `0.702×0.95=0.6669 mm²`；跨层信号通过局部与总量的键合密度容量筛选。
键合容量只是一种估计：bundle 均匀分布于端点投影外接框扩展区域，再按0.10 mm固定网格统计。未完成具体键合点排布、滑动窗口 DRC 或详细布线。

软约束的距离定义已由用户确认：**模块中心曼哈顿距离**，即 `|xa-xb|+|ya-yb|`。
每条约束的惩罚为 `weight × [(距离超限/max_dist)² + 不同层标志 + 不在指定层的端点数]`；对所有配对取平均，再乘配置的 `constraints` 权重。
Top 是软偏好，不能越过面积等硬约束；未知配对名称不会被静默忽略。

本次 Top 偏好的10个模块面积合计 **0.6902 mm² > 0.6669 mm²**，因此无法全部放 Top。
当前可选宽高比下，`is_int—ix` 和 `is_int_rf—ix` 的同层无重叠中心距离下界也超过0.20 mm。
`constraint_feasibility.json` 报告这些必要条件检查；通过检查不代表能同时满足所有要求。
扩大 `shape_aspects` 可改变距离下界，但不会消除 Top 面积冲突。输出保留每条违例及其幅度，不把有软违例的方案描述为完全满足约束。

## HotSpot 温度模型

使用上游 [HotSpot](https://github.com/uvahotspot/HotSpot) 的3D grid稳态模型，开启 `detailed_3D`。
实际材料传热和封装求解在 HotSpot C 程序中进行；Python 只生成输入、调用程序、解析输出及绘图。
每层按模块边界切分，完整覆盖 die，包括零功耗的空白硅区域；逐模块检查功率守恒。mm/µm 转为米，环境℃转为K，HotSpot结果再转回℃。
按[官方文件格式](https://github.com/uvahotspot/HotSpot/wiki/File-Types)生成 `.flp`、`.ptrace`、`.lcf` 和 `.config`；功耗 trace 必须按物理层号从小到大排序。
HotSpot 网格行0在上边缘；导出的温度 CSV 行0在下边缘，绘图和模块坐标一致。

当前堆栈：bottom硅50 µm → HB等效界面2 µm（1.4 W/m/K）→ top硅50 µm → TIM20 µm（4 W/m/K）→ HotSpot自带扩散器/散热器。
硅热导率130 W/m/K；封装参数取公开模板，配置中明确列出。散热器位于top侧，未启用背侧散热。
这些层厚、材料和封装数值均为估计，F2F金属/介质结构被等效成均匀层；需要实际工艺数据校准。
输入目前标注为动态功耗，程序直接使用给定值，未额外编造泄漏功耗或做温度—泄漏迭代。

上游温度输出原来保留0.01 K，随附源码仅提高文本输出精度至8位小数，防止帕累托排序把相近结果合并；没有修改热求解物理或收敛容限。
源码来源、快照SHA256及修改说明保存在 `third_party/HotSpot/PROVENANCE.md`，许可保存在 `LICENSE`。
输出精度不代表物理精度；温度和相近方案的排名依赖上述假设。

## 搜索、时序代价及帕累托输出

两层搜索：内层做位置、宽高比、换层及双模块交换退火，使用上一次 HotSpot 模块温度作为固定 RC 权重；外层对新候选实际调用 HotSpot，以完整温度/RC/约束得分接受或拒绝。
周期性重新排布和多模块扰动帮助离开局部极小值；相同布局复用真实 HotSpot 的计算结果。
没有在每次廉价几何扰动中预测温度。外层接受、最终评价和帕累托排序都使用该布局自己的真实 HotSpot 结果。
这是启发式候选搜索，不保证全局最优。

RC 排序代价采用 `[曼哈顿线长 + 跨层几何长度]² × [1+α×(端点温度最大值−参考温度)]`，按信号数及关键模块类别加权。
端点模块最高温度代替线路温度是一项估计。还把跨层信号比例乘100/333作为平均时钟预算代价。
缺少金属线单位RC、驱动/负载、缓冲器和路径图，**不能把这个代价换成真实 ns、路径加周期数、IPC 或 BIPS**。当前没有调用 gem5、McPAT 或 CACTI。

六组权重：balanced、wire、thermal、bond、timing、constraint，按乘数调整用户原有权重；配置、乘数及实际搜索预算写入结果。
联合最小化五个目标：信号加权平均线长、跨层信号数、时序代价、软约束惩罚、HotSpot最高温度。
先选择约束、温度、时序的代表方案及均衡方案，再补充前沿分散点；只选严格非支配方案，前沿不足4个就输出实际数量。

输出：

- `manifest.json`、`effective_config.json`、`input_config.yaml`：运行设置及物理假设。
- `constraint_feasibility.json`：Top面积冲突和同层距离下界。
- `pareto_candidates.csv`、`pareto.svg`：所有候选的五目标指标及4张温度对比散点图。
- `search_history.json`：每轮候选、实际温度、接受结果、是否使用缓存。
- `layout_01` 等：布局SVG/JSON，统一色标的温度SVG，64×64×2温度CSV，逐条约束违例CSV。
- `layout_0N/hotspot`：该方案完整的 HotSpot 输入、输出、运行命令和stdout/stderr。
- `hotspot_pool`：候选全集的热仿真输入/输出，可追溯和复算。

真实 HotSpot 验证示例保存在 [examples/hotspot_20261008](../examples/hotspot_20261008/README.md)。旧 `results` / `pareto_results` 代理输出已从当前版本移除。
三倍原始模块面积会超出两层面积预算；本次附件仍使用约1.7倍的几何面积，没有为满足新增约束擅自缩小模块。
