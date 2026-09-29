# MCP 实现验证记录

## 通过的测试

执行：

```powershell
python -m pytest tests/test_mcp_server.py tests/test_mcp_protocol.py mcp_server/test_tasks.py tests/test_config_advisor.py tests/test_config_aggregator.py tests/test_config_parser.py tests/test_core_logic.py tests/test_framework_adapters.py -q
```

结果：**66 passed**（Windows / Python 3.13.9）。其中 MCP 新增 13 项测试。

覆盖范围：

- 真实 MCP STDIO 握手、22 个工具注册、调用成功与错误响应。
- 服务端导入不加载 PySide6 和 torch。
- 中文路径项目创建/重开、数据集统计、确定性划分、非法输入与重复样本。
- 使用真实 mmengine 在独立子进程中生成配置，验证迭代次数、路径和自定义模块文件。
- 真实 Python 子进程的日志解析、增量游标、非零退出、启动前/运行中取消及退出清理。
- 评估命令与指标适配、推理请求参数、进度处理、缺少结构化结果的失败识别。
- 禁止模拟推理；Core 返回失败但遗留部分输出时仍判为失败。

## 测试中修正的问题

- 推理不能只检查输出文件存在，必须同时检查 Core 返回 success。
- 既有回归测试的四处中文消息断言已与当前 Core 文本对齐。
- 既有 mmengine Mock 补齐内部子模块，避免依赖测试执行顺序。
- 根 .gitignore 忽略 test_*.py，新增局部忽略规则例外，确保新增测试能纳入版本控制。
  未修改用户已有的根 .gitignore 改动。

## 尚未通过验收的范围

全量 tests 曾发现两个与 MCP 无关的既有 UI 测试断言过时，未修改 UI 或其测试：

- test_backbone_choices 假定显示所有 18 个骨干，但当前 UI 按选定算法显示 4 个。
- test_tab_names 假定中文标签，但当前标签为 General/Optimizer/Checkpoint/Augmentation。

因此不能宣称仓库全量 UI 回归通过。

当前宿主无 PyTorch/MMSegmentation/GDAL 训练推理环境及验收模型权重，
尚未进行真实 GPU 训练、真实 checkpoint 评估或实际大幅 GeoTIFF 推理。
评估/推理的协议、参数和错误边界已测试，模型数值正确性仍需在 B 层验证。
SSE 启动选项已实现，但本轮协议端到端测试使用的是推荐的 STDIO 传输。
