---
description: 运行所有单元测试并验证模块导入，用于代码修改后的自动验证
---

// turbo-all

1. 设置 UTF-8 编码环境
   ```
   $env:PYTHONIOENCODING='utf-8'
   ```

2. 运行配置解析器测试
   ```
   $env:PYTHONIOENCODING='utf-8'; python tests/test_config_parser.py
   ```

3. 验证 dataset_metadata 模块导入
   ```
   $env:PYTHONIOENCODING='utf-8'; python -c "from core.dataset_metadata import _analyze_sample_fully, ISSUE_FILE_MISSING; print('dataset_metadata OK')"
   ```

4. 验证 skill_geodata_utils 导入和功能
   ```
   $env:PYTHONIOENCODING='utf-8'; python -c "from skills.skill_geodata_utils import gdal_data_to_opencv_data; import numpy as np; d=np.random.rand(3,4,4); r=gdal_data_to_opencv_data(d); assert r.shape==(4,4,3); print('skill_geodata_utils OK')"
   ```

5. 验证 config_parser 模块导入
   ```
   $env:PYTHONIOENCODING='utf-8'; python -c "from core.config_parser import ConfigParser; print('config_parser OK')"
   ```
