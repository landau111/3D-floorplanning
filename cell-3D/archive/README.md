# 历史代码与源码快照

当前入口是上一级 run.py；归档不参与默认运行。

source_snapshots/2026-10-13/published_flat 保存提交 5909cb90035f478c0e04b45254106e368419f801 的已发布平铺源码，原字节不变。旧发布 manifest 的 basename SHA256 可在这里核对：run_layout.py 主算法；layout_input.py/yaml_subset.py 解析；layout_hotspot.py 热接口；layout_svg.py 图表；layout_baseline.json IPC 基线。

该快照还保留原 config.yaml.json/folding_dse_annealing_cfg.yaml（输入）、test_layout.py（验证）、build_layout_bundle.py（打包）、run_layout.cmd/.sh（启动）、requirements_portable.txt（依赖）、README.md/PORTABLE_RUN.md（旧目录说明）、LAYOUT_RUN_RESULT.md（原结果解析）、PORTABILITY_VALIDATION.json（原移植证据）及 .gitignore/.gitattributes（原版本控制规则）。这些名称和路径都是当时的版本，只用于审计，不作为当前启动入口。

legacy 从原 cell3d 收集早期矩形/拼图代码。ROOT/基线路径依赖原平铺结构，**不要直接在 archive 中运行**；用完整仓库的重放工具建立新结果目录：

```powershell
python tools/legacy_runner.py test-model
python tools/legacy_runner.py test-puzzle
python tools/legacy_runner.py simulate --quick
python tools/legacy_runner.py puzzle
```

工具复制旧源码、历史输入结果和 gem5 基线到 results 日期目录的 work，再执行；不覆盖原始归档，legacy_replay 不更新最新正式入口。puzzle 默认完整搜索较慢；旧图表另需旧 requirements/字体环境。便携 ZIP 不含全部 archive，重放需完整 Git 仓库。

|legacy 文件|用途|
|---|---|
|simulate.py|早期矩形场景合成 cell、梯度放置、路由与性能代理|
|puzzle.py|早期非矩形区域划分与优化|
|test_model.py、test_puzzle.py|两代历史数学/合法性验证|
|make_figures.py、puzzle_figures.py|两代出版图生成|
|render_figures.py|历史图转换|
|write_summary.py|历史结果说明生成|
|input_inventory.py|历史输入参数清单|
|config.json、puzzle_config.json|早期合成实验参数，不是今晚最终配置|
|config_completed.yaml、inputs_complete.json|旧补全估算输入；用户后续采用原格式，此处只保留历史|
|gem5_stats.json|旧脚本要求的完整 gem5 统计副本|
|requirements.txt|历史依赖，当前依赖见根目录 requirements|
|README.md|原平铺目录说明|
|RESULTS.md|早期矩形结果分析|
|PARAMETERS.md|旧估算参数来源|
|PUZZLE_METHOD.md|旧拼图数学方法|
|FIGURES.md|旧图表清单|
|CONFIG_COMPLETION_NOTES.md|旧配置补全过程|

对应结果在 results/2026-09-25/{rectangular,puzzle}。旧文档相对路径代表原目录。部分开发运行缺完整源码快照，不保证当前源码逐数复现；旧输入/模型不同，历史“可行”不代表今晚布线可行。
