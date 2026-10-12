# changed_config

日期：2026-10-13；分类：`environment_validation`；状态：`complete`。

日期依据：original directory date。

**本次没有布线可行的优化候选。selected 文件是诊断候选，不代表后端可用最优解；正式帕累托集合为空。**

[打开布局与温度图](index.html) · [完整数学分析](../../../docs/ALGORITHM_2026-10-13.md)

|方案|工作频率 GHz|功耗 W|工作温度 °C|溢出 tracks|可行|
|---|---:|---:|---:|---:|---|
|initial|1.1821|0.4545|33.337|10920.25|False|
|balanced|1.3354|0.5158|33.977|9332.25|False|
|timing|1.3354|0.5159|33.978|9206.75|False|
|thermal|1.3338|0.5154|33.935|9816.50|False|

温度/功耗对应降频后的工作点；标称频率比较见 metrics.csv 的 nominal 列及算法解析。

|文件/目录|作用|
|---|---|
|[assumptions.json](assumptions.json)|本次实际使用的估算/派生参数|
|[backend_margin.json](backend_margin.json)|后端留白、利用率、padding、时钟预留统计|
|[balanced.npz](balanced.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[balanced_module_temperatures.csv](balanced_module_temperatures.csv)|各模块输入参考温度和本次计算平均温度|
|[balanced_trace.json](balanced_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[before_after.svg](before_after.svg)|优化前后逐 cell 布局图|
|[effective_input.json](effective_input.json)|解析、名称规范化后的实际输入及冲突提示|
|[index.html](index.html)|本次运行交互/图表浏览入口|
|[initial.npz](initial.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[initial_module_temperatures.csv](initial_module_temperatures.csv)|各模块输入参考温度和本次计算平均温度|
|[initial_trace.json](initial_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[input_annealing_cfg.yaml](input_annealing_cfg.yaml)|本次功耗、连接、热堆栈等辅助输入原件|
|[input_config.yaml.json](input_config.yaml.json)|本次最终模块布局输入原件|
|[manifest.json](manifest.json)|运行参数、环境、源码 SHA256、可行性与候选选择记录|
|[metrics.csv](metrics.csv)|所有候选的功耗、温度、频率、IPC/BIPS、时序和布线指标|
|[module_shapes.csv](module_shapes.csv)|各模块连通、孔洞、面积误差、长宽比和紧凑度检查|
|[pareto.svg](pareto.svg)|帕累托诊断图；不可行候选不会进入正式前沿|
|[README.md](README.md)|本次运行分类、指标与逐文件说明（自动生成）|
|[regions.svg](regions.svg)|非矩形模块归属区域图（区域覆盖率不等于标准单元利用率）|
|[selected_bonds.csv](selected_bonds.csv)|诊断候选实际分配的跨层 bond 坐标|
|[selected_cells.csv](selected_cells.csv)|诊断候选逐 cell 的模块、层、坐标和可移动属性|
|[selected_route_guides.csv](selected_route_guides.csv)|外部连接的 XY/YX 路径及主干层|
|[selected_soft_constraints.csv](selected_soft_constraints.csv)|源配置距离与层偏好约束的达成情况|
|[shape_trace.json](shape_trace.json)|区域优化迭代和合法检查点选择记录|
|[temperature.svg](temperature.svg)|两层温度分布图|
|[thermal.npz](thermal.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[thermal_module_temperatures.csv](thermal_module_temperatures.csv)|各模块输入参考温度和本次计算平均温度|
|[thermal_trace.json](thermal_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[timing.npz](timing.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[timing_module_temperatures.csv](timing_module_temperatures.csv)|各模块输入参考温度和本次计算平均温度|
|[timing_trace.json](timing_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
