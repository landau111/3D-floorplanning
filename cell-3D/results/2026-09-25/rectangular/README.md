# rectangular

日期：2026-09-25；分类：`legacy`；状态：`complete`。

日期依据：original files modification date; historical manifest has no explicit run timestamp。

|方案|工作频率 GHz|功耗 W|工作温度 °C|溢出 tracks|可行|
|---|---:|---:|---:|---:|---|
|A_split__baseline|1.2722|6.0426|71.883|5121.00|False|
|A_split__routing_only|1.2722|6.0426|71.883|3595.00|False|
|A_split__balanced|1.3414|6.1417|71.615|0.00|True|
|A_split__timing|1.2688|5.8230|70.262|0.00|True|
|A_split__thermal|1.3504|6.2030|71.851|0.00|True|
|B_critical_local__baseline|1.0911|5.2816|68.944|5277.00|False|
|B_critical_local__routing_only|1.0911|5.2816|68.944|3560.00|False|
|B_critical_local__balanced|1.2032|5.5826|69.714|0.00|True|
|B_critical_local__timing|1.1369|5.2900|68.627|0.00|True|
|B_critical_local__thermal|1.2482|5.7888|70.524|0.00|True|
|C_hot_top__baseline|0.9731|4.7994|67.557|7307.00|False|
|C_hot_top__routing_only|0.9731|4.7994|67.557|4043.00|False|
|C_hot_top__balanced|1.0866|5.1221|68.477|0.00|True|
|C_hot_top__timing|1.0376|4.8995|67.807|0.00|True|
|C_hot_top__thermal|1.0752|5.0974|68.268|50.00|False|
|A_split__thermal__seed17|1.3614|6.2484|72.030|0.00|True|
|A_split__thermal__seed41|1.3467|6.1877|71.764|0.00|True|

温度/功耗对应降频后的工作点；标称频率比较见 metrics.csv 的 nominal 列及算法解析。

|文件/目录|作用|
|---|---|
|[A_split__balanced.npz](A_split__balanced.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[A_split__balanced_trace.json](A_split__balanced_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[A_split__baseline.npz](A_split__baseline.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[A_split__baseline_trace.json](A_split__baseline_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[A_split__routing_only.npz](A_split__routing_only.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[A_split__routing_only_trace.json](A_split__routing_only_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[A_split__thermal.npz](A_split__thermal.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[A_split__thermal__seed17.npz](A_split__thermal__seed17.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[A_split__thermal__seed17_trace.json](A_split__thermal__seed17_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[A_split__thermal__seed41.npz](A_split__thermal__seed41.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[A_split__thermal__seed41_trace.json](A_split__thermal__seed41_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[A_split__thermal_trace.json](A_split__thermal_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[A_split__timing.npz](A_split__timing.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[A_split__timing_trace.json](A_split__timing_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[A_split_modules.csv](A_split_modules.csv)|历史运行原始数据/图表；原算法说明见 archive/legacy 中的文档|
|[B_critical_local__balanced.npz](B_critical_local__balanced.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[B_critical_local__balanced_trace.json](B_critical_local__balanced_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[B_critical_local__baseline.npz](B_critical_local__baseline.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[B_critical_local__baseline_trace.json](B_critical_local__baseline_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[B_critical_local__routing_only.npz](B_critical_local__routing_only.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[B_critical_local__routing_only_trace.json](B_critical_local__routing_only_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[B_critical_local__thermal.npz](B_critical_local__thermal.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[B_critical_local__thermal_trace.json](B_critical_local__thermal_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[B_critical_local__timing.npz](B_critical_local__timing.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[B_critical_local__timing_trace.json](B_critical_local__timing_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[B_critical_local_modules.csv](B_critical_local_modules.csv)|历史运行原始数据/图表；原算法说明见 archive/legacy 中的文档|
|[best_bonds.csv](best_bonds.csv)|历史运行原始数据/图表；原算法说明见 archive/legacy 中的文档|
|[best_cells.csv](best_cells.csv)|历史运行原始数据/图表；原算法说明见 archive/legacy 中的文档|
|[best_layout.svg](best_layout.svg)|历史运行原始数据/图表；原算法说明见 archive/legacy 中的文档|
|[best_route_guides.csv](best_route_guides.csv)|历史运行原始数据/图表；原算法说明见 archive/legacy 中的文档|
|[C_hot_top__balanced.npz](C_hot_top__balanced.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[C_hot_top__balanced_trace.json](C_hot_top__balanced_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[C_hot_top__baseline.npz](C_hot_top__baseline.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[C_hot_top__baseline_trace.json](C_hot_top__baseline_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[C_hot_top__routing_only.npz](C_hot_top__routing_only.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[C_hot_top__routing_only_trace.json](C_hot_top__routing_only_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[C_hot_top__thermal.npz](C_hot_top__thermal.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[C_hot_top__thermal_trace.json](C_hot_top__thermal_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[C_hot_top__timing.npz](C_hot_top__timing.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[C_hot_top__timing_trace.json](C_hot_top__timing_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[C_hot_top_modules.csv](C_hot_top_modules.csv)|历史运行原始数据/图表；原算法说明见 archive/legacy 中的文档|
|[figures](figures)|历史出版图：PNG/SVG/PDF，保留原始版本|
|[manifest.json](manifest.json)|运行参数、环境、源码 SHA256、可行性与候选选择记录|
|[metrics.csv](metrics.csv)|所有候选的功耗、温度、频率、IPC/BIPS、时序和布线指标|
|[README.md](README.md)|本次运行分类、指标与逐文件说明（自动生成）|
|[restarts.csv](restarts.csv)|历史运行原始数据/图表；原算法说明见 archive/legacy 中的文档|
|[sensitivity.csv](sensitivity.csv)|历史运行原始数据/图表；原算法说明见 archive/legacy 中的文档|
