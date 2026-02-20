---
description: 验证所有核心模块和 Skills 的导入链完整性
---

// turbo-all

1. 验证 skills 包导入
   ```
   $env:PYTHONIOENCODING='utf-8'; python -c "from skills.skill_image_processing import VOC_PALETTE, apply_colormap, apply_linear_stretch; print('skill_image_processing OK:', len(VOC_PALETTE), 'colors')"
   ```

2. 验证 skills 包导入（sample_analysis）
   ```
   $env:PYTHONIOENCODING='utf-8'; python -c "from skills.skill_sample_analysis import analyze_sample_fully, ISSUE_LEVELS; print('skill_sample_analysis OK:', len(ISSUE_LEVELS), 'issue types')"
   ```

3. 验证 skills 包导入（geodata_utils）
   ```
   $env:PYTHONIOENCODING='utf-8'; python -c "from skills.skill_geodata_utils import gdal_data_to_opencv_data; print('skill_geodata_utils OK')"
   ```

4. 验证 core 模块导入链
   ```
   $env:PYTHONIOENCODING='utf-8'; python -c "from core.config_parser import ConfigParser; from core.dataset_metadata import DatasetMetadataManager; print('core modules OK')"
   ```
