# 模块级双 die 折叠布局探索器

`config.yaml` 根据用户提供的参数草案构造。草案给出 1.10 × 0.91 mm die、每层面积上限 0.702 mm²、`area_margin=0.95`、两个 L2 宏固定在下层、14 个可移动模块、5 µm F2F pitch、`max_density_per_mm2=20000`，以及 `l2_b0`—`l2_ctl` 的 5000 个信号。其余矩形/面积、锚点、功耗和互联数量都是**特意模糊化的合成假设**，不代表 C910 的真实数据。附件中的“你自己随机参数填上”是待补空位，不是求解器指令。

## 运行

Python 3.10+；随附的 `config.yaml` 是 JSON 格式的 YAML 1.2 文件，因此只用标准库。普通 YAML 语法需要安装 PyYAML。

```powershell
python folding_dse/optimize.py folding_dse/config.yaml --output folding_dse/results
python folding_dse/test_optimize.py
```

本机若 `python` 指向 Windows Store 占位程序，请换用本机已安装的 Python 3.10+ 可执行文件运行相同命令。

可传 `--steps`、`--restarts` 调整搜索预算。程序每次读取配置；改模块面积、锚点、功耗、固定位置、网络条目或目标权重后重跑即可。`best_layout.json` 保存指标、模块坐标、搜索记录及模型限制；`best_layout.csv` 可导入表格；`best_layout.svg` 显示上下两层。固定种子可重现结果。若无法排布或密度代理无可行解，程序会报错。

## 模型与约束

- 硬模块的 `rect=[x,y,w,h]` 固定不动，坐标原点在 die 左下角。软模块的 `anchor=[x,y]` 是中心偏好的参考点，可换层、平移，并在五种宽高比中选择，面积不变。
- 每层矩形必须在 die 内、互不重叠且保持 0.008 mm 间距。每层模块面积必须 ≤ `0.702 × 0.95 = 0.6669 mm²`。这是模块面积上限，并非自动证明标准单元可实现的利用率。
- `max_density_per_mm2` **按 F2F 信号键合解释**。每个跨层互联 bundle 假设均匀分布于两端模块投影外接框并向外扩 0.05 mm；在对齐的 0.10 mm 窗口计算平均密度。容量取 5 µm pitch 对应的 40,000/mm² 与 20,000/mm² 较小值，并额外预留 20%，即 16,000/mm²。还检查整片总数上限。这只是筛选代理，未确定每个键合点的位置，也未完成滑动窗口 DRC。
- 退火目标结合按信号数加权的模块中心曼哈顿线长、跨层信号比例、平滑功率热点指数、锚点偏移与两层总功耗差。权重都在配置中。每个 restart 独立随机排布，再进行形状、位置、层的随机扰动与降温接受；保存所有探索中代理约束合格的最低分方案。**它是启发式最优候选，不保证全局最优。**
- 热点指数并非摄氏温度；线长并非时序；跨层信号数并非实际键合数。真实签核需要宏 pin、网表、时序约束、工艺与材料、供电网络、bond 预留和详细布线。配置里的机密参数可用同一单位和结构的脱敏数据替换。

## 扩大面积与多目标搜索

原配置模块面积合计 0.7270 mm²；把**全部模块**乘 3 后是 2.1810 mm²。两层允许的面积合计是 `2 × 0.702 × 0.95 = 1.3338 mm²`，所以三倍方案在面积这一必要条件上就不成立。理论统一倍率上界为 `1.3338 / 0.7270 = 1.8347`，尚未计入模块形状与间距。`make_enlarged.py` 对三倍输入明确报不可行。

当前 [config_enlarged.yaml](config_enlarged.yaml) 对**每个模块**统一扩大 1.7 倍，总面积 1.2359 mm²，占面积预算约 92.7%。硬宏保持原宽高比；因原坐标也属猜测，右侧 L2 宏随宽度增加向左调整，以维持离右边界 0.035 mm。

```powershell
python folding_dse/make_enlarged.py folding_dse/config.yaml folding_dse/config_enlarged.yaml --factor 1.7
python folding_dse/explore.py folding_dse/config_enlarged.yaml
```

`explore.py` 用 balanced、wire、thermal、bond、anchor 五组权重做多次退火；加入双模块中心/层交换变异，帮助高密度排布跳出单模块移动的障碍。保存各次搜索中间改进点，对**信号数加权平均线长、跨层信号数、最高温度**做严格帕累托筛选。`pareto_candidates.csv` 是候选全集；`pareto.svg` 是两张散点图；`manifest.json` 记录入选的四个方案；每个 `layout_0N` 目录都有布局、温度图、温度网格 CSV、HotSpot 输入文件。四幅温度图共用颜色范围。

默认温度后端是 2 层、10×12 网格的稳态导热网络。功率按模块与网格的真实重叠面积投影，数值迭代到残差阈值，并检查功率守恒。环境温度、封装热阻、层内/层间/顶层散热导纳都是**合成估计值**，所以摄氏度结果只用于同配置方案的趋势比较，不能当作实测温度或 HotSpot 输出。

## 直接调用 HotSpot

热接口依据 HotSpot [官方源码](https://github.com/uvahotspot/HotSpot) 和 [文件格式说明](https://github.com/uvahotspot/HotSpot/wiki/File-Types)：每层完整矩形 floorplan（含空白区）、功耗 `.ptrace`、从散热侧到背侧的 `.lcf`。有 HotSpot 可执行文件时，指定其路径即可让**全部候选**用 HotSpot 网格稳态温度重新做帕累托排序，并生成相应温度图：

```powershell
python folding_dse/explore.py folding_dse/config_enlarged.yaml --hotspot-exe C:\path\to\hotspot.exe
```

本机未找到已安装的 HotSpot；官方源码的网络获取也未成功。本次 `pareto_results` 的温度后端字段为 `assumed_conductance_proxy`，不是 HotSpot。HotSpot 的材料、硅层厚度与默认封装参数仍需用真实堆栈校准，才能用于物理温度判断。`--hotspot-exe` 指定的程序若报错，流程会保留 stdout/stderr 并失败，不会把备用模型误称为 HotSpot。

## 下一步算法改进

现有退火每次扰动后重算全部连接和热热点指数，适合目前 16 模块规模。模块数或网络边数增大后，可缓存未受影响的连接项与网格功率，做增量评分。更大的收益是用当前便宜的代理筛选大候选池，再对帕累托前沿调用已校准 HotSpot、真实 pin/走线估计和时序模型做第二阶段局部搜索；否则代理目标与物理目标之间的排序偏差会限制搜索质量。高占用率下还可以用序列对、B* 树或约束规划生成初始非重叠布局，减少随机贪心构造失败。当前结果没有这些第二阶段验证。
