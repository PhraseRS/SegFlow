# -*- coding: utf-8 -*-
"""
核心配置聚合器 (Config Aggregator)

负责收集并合并来自主界面多个配置组件的数据，
根据明确的优先级策略生成最终的训练配置字典。

Training Roadmap Phase 4, Task X
"""

from typing import Dict, Any


class ConfigAggregator:
    """
    配置聚合器

    合并策略 (优先级从低到高):
    1. mmseg_params 默认值 (AdvancedConfigWidget 基础值)
    2. AdvancedConfigWidget 面板用户修改的值
    3. HyperparamTabsWidget 基础超参数
    4. AdvisorConfigWidget 智能推荐的强制锁定参数
    5. AdvancedConfigWidget 底部 JSON 手写覆写字典
    """

    def __init__(self):
        pass

    def aggregate(self,
                  advanced_params: Dict[str, Any],
                  hyper_params: Dict[str, Any],
                  advisor_params: Dict[str, Any],
                  json_overrides: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行合并流程
        
        Args:
            advanced_params: AdvancedConfigWidget 获取的面板参数 (优先级1,2)
            hyper_params: HyperparamTabsWidget 获取的超参数 (优先级3)
            advisor_params: AdvisorConfigWidget 获取的推荐参数 (优先级4)
            json_overrides: JSON 文本框获取的强制覆写参数 (优先级5)
            
        Returns:
            Dict: 合并后的完整字典
        """
        # 1 & 2: 基础合并 (直接深拷贝 advanced_params)
        final_config = {}
        for k, v in advanced_params.items():
            final_config[k] = v

        # 3: HyperparamTabsWidget 覆写
        # 建立映射关系 (左侧为 hyper_params 的 key，右侧为 advanced_params 中对应的 key)
        hyper_to_advanced_map = {
            'batch_size': 'batch_size',
            'max_iters': 'max_iters',
            'lr': 'learning_rate',
            'optimizer': 'optimizer',
            'save_interval': 'checkpoint_interval',
            'num_workers': 'num_workers', # 如果先进面板有加
        }
        
        for hk, hv in hyper_params.items():
            if hk in hyper_to_advanced_map:
                ak = hyper_to_advanced_map[hk]
                final_config[ak] = hv
            else:
                final_config[hk] = hv # 保留未映射的超参数

        # 4: AdvisorConfigWidget 智能推荐强制覆写
        if advisor_params:
            if advisor_params.get('in_channels') is not None:
                final_config['input_channels'] = advisor_params['in_channels']
                final_config['in_channels'] = advisor_params['in_channels']
            
            crop = advisor_params.get('crop_size')
            if crop is not None:
                # 检查是 tuple 还是 int
                if isinstance(crop, (tuple, list)):
                    final_config['crop_size'] = crop[0]
                else:
                    final_config['crop_size'] = crop

        # 5: JSON 手写强制覆写 (最高优先级)
        # 支持点号分割的多层级字典强制挂载，或者直接更新浅层
        if json_overrides:
            for jk, jv in json_overrides.items():
                # 如果这个以 . 分割的 key 本身就存在于原字典(由于 advanced_params 是扁平的)，直接覆盖扁平键
                if jk in final_config:
                    final_config[jk] = jv
                else:
                    self._apply_nested_override(final_config, jk, jv)

        return final_config

    def _apply_nested_override(self, config: Dict[str, Any], key_path: str, value: Any):
        """处理形如 'model.decode_head.dropout_ratio' 的树状覆写"""
        parts = key_path.split('.')
        if len(parts) == 1:
            config[parts[0]] = value
            return
            
        current = config
        for i, part in enumerate(parts[:-1]):
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
            
        current[parts[-1]] = value
