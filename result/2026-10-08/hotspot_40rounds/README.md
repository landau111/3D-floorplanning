# 真实 HotSpot 验证示例（2026-10-08）

使用脱敏输入，6组评分权重、每组40轮、每轮1000次几何扰动、1次重启。
实际调用 HotSpot 239次（另1次复用相同布局），得到57个五目标非支配候选，选出下面4个代表布局。
这是一次搜索样例；正式默认配置为2次重启，不能把本例当作全局最优或真实芯片温度。

| 方案 | 最高温度℃ | 来源profile | 软约束违例条数 | 布局图 | 温度图 | 违例明细 | 模块坐标 |
| --- | ---: | --- | ---: | --- | --- | --- | --- |
| 1 | 38.643 | timing | 12 | [布局](layout_01/layout.svg) | [温度](layout_01/temperature.svg) | [明细](layout_01/constraint_violations.csv) | [坐标](layout_01/module_coordinates.csv) |
| 2 | 36.886 | balanced | 12 | [布局](layout_02/layout.svg) | [温度](layout_02/temperature.svg) | [明细](layout_02/constraint_violations.csv) | [坐标](layout_02/module_coordinates.csv) |
| 3 | 41.283 | constraint | 12 | [布局](layout_03/layout.svg) | [温度](layout_03/temperature.svg) | [明细](layout_03/constraint_violations.csv) | [坐标](layout_03/module_coordinates.csv) |
| 4 | 38.224 | timing | 12 | [布局](layout_04/layout.svg) | [温度](layout_04/temperature.svg) | [明细](layout_04/constraint_violations.csv) | [坐标](layout_04/module_coordinates.csv) |

profile表示生成候选时的搜索权重组，不等同于最终代表方案的评选类别。
违例条数相同不代表违例程度相同；方案1的平均软约束惩罚更低。部分要求存在几何冲突，见 [必要条件检查](constraint_feasibility.json)。

## 查看

- [帕累托图](pareto.svg)：五维非支配判定，四个二维投影。
- [所有入选方案模块坐标](all_module_coordinates.csv)：每个方案16个模块，共64行；各方案目录另有 `module_coordinates.csv`。坐标单位mm，原点在各层左下角，x/y为模块左下角，w/h为宽高，并附中心坐标。
- [候选全集指标](pareto_candidates.csv)：239个候选，包含前沿标志和选中编号。
- [运行记录](manifest.json)、[有效配置](effective_config.json)、[原始配置](input_config.yaml)、[搜索过程](search_history.json)。
- 每个 `layout_0N/hotspot/` 保留该方案的完整输入、温度网格输出、运行命令和日志，可独立复算。

本例仅保留4个代表方案的HotSpot原始文件，候选全集的 `hotspot_pool` 缓存未进入Git，以减少重复文件。
没有改变温度或布局数据。JSON中的机器绝对路径已改为可移植的相对路径；保留原始HotSpot二进制SHA256作为运行来源记录。
不同编译器/平台构建的二进制SHA256可能不同，不能将其误认为复算温度必须完全相同。

## 复算

在仓库根目录运行（Linux/WSL）：

```bash
make hotspot
DSE_ROOT="$(pwd)"
cd result/2026-10-08/hotspot_40rounds/layout_01/hotspot
"$DSE_ROOT/third_party/HotSpot/hotspot" -c hotspot.config -grid_layer_file stack.lcf -f bottom.flp -p power.ptrace -steady_file rerun.steady -grid_steady_file rerun.grid.steady
```

`input_config.yaml` 是当时运行的配置快照；其中隐式采用的5种宽高比与当前默认值相同。
原始HotSpot温度单位K、网格行0在顶部；导出的 `temperature.csv` 使用℃和从底部开始的行号。
四幅温度图共用色标。层结构/材料/封装仍是估计，输入总功耗0.845 W，未额外增加泄漏功耗。

详细运行和调参步骤参见 [操作手册](../../../操作手册.md)。
