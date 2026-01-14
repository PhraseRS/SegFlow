"""
MMSegmentation 配置文件解析器
用于解析 .py 配置文件并提取模型信息、类别和调色板
增强版本 - 支持多种配置格式和健壮的错误处理
"""

import os
import re
import ast
from typing import Optional, Dict, Any, List, Tuple


class ConfigParser:
    """MMSegmentation 配置文件解析器 - 增强版本"""
    
    def __init__(self):
        self.config_path: Optional[str] = None
        self.model_name: Optional[str] = None
        self.model_type: Optional[str] = None
        self.backbone: Optional[str] = None
        self.num_classes: Optional[int] = None
        self.classes: Optional[List[str]] = None
        self.palette: Optional[List[Tuple[int, int, int]]] = None
        
    def parse_config_file(self, config_path: str) -> Tuple[Optional[List[str]], Optional[List[Tuple[int, int, int]]]]:
        """
        解析配置文件，提取类别和调色板信息
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            (classes, palette) 元组，解析失败时返回 (None, None)
        """
        try:
            if not os.path.exists(config_path):
                return None, None
            
            if not config_path.endswith('.py'):
                return None, None
            
            self.config_path = config_path
            
            # 读取文件内容
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(config_path, 'r', encoding='gbk') as f:
                        content = f.read()
                except:
                    return None, None
            
            # 解析类别和调色板信息（不抛出异常）
            try:
                self._parse_classes_and_palette(content)
            except Exception as e:
                print(f"类别和调色板解析警告: {e}")
            
            return self.classes, self.palette
            
        except Exception as e:
            print(f"配置文件解析失败: {e}")
            return None, None
    
    def extract_model_name(self, config_path: str) -> str:
        """提取模型名称"""
        try:
            if not os.path.exists(config_path):
                return "Unknown Model"
            
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析模型信息
            self._parse_model_info(content)
            
            if self.model_name:
                return self.model_name
            
            # 从文件名推断
            return self._infer_model_name_from_filename(config_path)
            
        except Exception:
            return os.path.splitext(os.path.basename(config_path))[0]
    
    def extract_model_type(self, config_path: str) -> Optional[str]:
        """提取模型类型"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self._parse_model_info(content)
            return self.model_type
            
        except Exception:
            return None
    
    def _parse_classes_and_palette(self, content: str):
        """
        智能解析类别和调色板信息
        支持多种格式：
        1. CLASSES = [...]
        2. PALETTE = [...]
        3. metainfo = dict(classes=(...), palette=[...])
        4. 任意嵌套字典中的相关字段
        """
        # 方法1: 尝试直接解析 CLASSES 和 PALETTE 变量
        self.classes = self._extract_classes_direct(content)
        self.palette = self._extract_palette_direct(content)
        
        # 方法2: 如果方法1失败，尝试从 metainfo 解析
        if not self.classes or not self.palette:
            classes_meta, palette_meta = self._extract_from_metainfo(content)
            if not self.classes:
                self.classes = classes_meta
            if not self.palette:
                self.palette = palette_meta
        
        # 方法3: 如果仍然失败，尝试从任意字典中搜索
        if not self.classes or not self.palette:
            classes_dict, palette_dict = self._extract_from_any_dict(content)
            if not self.classes:
                self.classes = classes_dict
            if not self.palette:
                self.palette = palette_dict
        
        # 方法4: 尝试从 dataset_type 或 data 配置中提取
        if not self.classes or not self.palette:
            classes_data, palette_data = self._extract_from_dataset_config(content)
            if not self.classes:
                self.classes = classes_data
            if not self.palette:
                self.palette = palette_data
    
    def _extract_classes_direct(self, content: str) -> Optional[List[str]]:
        """提取直接定义的 CLASSES 变量"""
        patterns = [
            r'CLASSES\s*=\s*\[(.*?)\]',
            r'CLASSES\s*=\s*\((.*?)\)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                classes_str = match.group(1)
                return self._parse_string_list(classes_str)
        
        return None
    
    def _extract_palette_direct(self, content: str) -> Optional[List[Tuple[int, int, int]]]:
        """提取直接定义的 PALETTE 变量"""
        patterns = [
            r'PALETTE\s*=\s*(\[(?:[^\[\]]*\[[^\[\]]*\][^\[\]]*)*\])',
            r'PALETTE\s*=\s*(\((?:[^\(\)]*\([^\(\)]*\)[^\(\)]*)*\))',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                palette_str = match.group(1)
                try:
                    result = ast.literal_eval(palette_str)
                    if isinstance(result, (list, tuple)):
                        palette = []
                        for item in result:
                            if isinstance(item, (list, tuple)) and len(item) == 3:
                                palette.append((int(item[0]), int(item[1]), int(item[2])))
                        if palette:
                            return palette
                except:
                    return self._parse_palette_list(palette_str)
        
        return None
    
    def _extract_from_metainfo(self, content: str) -> Tuple[Optional[List[str]], Optional[List[Tuple[int, int, int]]]]:
        """从 metainfo 字典中提取类别和调色板"""
        metainfo_pattern = r'metainfo\s*=\s*dict\((.*?)\)'
        match = re.search(metainfo_pattern, content, re.DOTALL)
        
        if not match:
            return None, None
        
        metainfo_content = match.group(1)
        
        # 提取 classes
        classes = None
        classes_patterns = [
            r'classes\s*=\s*\[(.*?)\]',
            r'classes\s*=\s*\((.*?)\)',
        ]
        for pattern in classes_patterns:
            classes_match = re.search(pattern, metainfo_content, re.DOTALL)
            if classes_match:
                classes = self._parse_string_list(classes_match.group(1))
                break
        
        # 提取 palette
        palette = None
        palette_patterns = [
            r'palette\s*=\s*(\[(?:[^\[\]]*\[[^\[\]]*\][^\[\]]*)*\])',
            r'palette\s*=\s*(\((?:[^\(\)]*\([^\(\)]*\)[^\(\)]*)*\))',
        ]
        for pattern in palette_patterns:
            palette_match = re.search(pattern, metainfo_content, re.DOTALL)
            if palette_match:
                palette_str = palette_match.group(1)
                try:
                    result = ast.literal_eval(palette_str)
                    if isinstance(result, (list, tuple)):
                        palette = []
                        for item in result:
                            if isinstance(item, (list, tuple)) and len(item) == 3:
                                palette.append((int(item[0]), int(item[1]), int(item[2])))
                        if palette:
                            break
                except:
                    palette = self._parse_palette_list(palette_str)
                    if palette:
                        break
        
        return classes, palette
    
    def _extract_from_any_dict(self, content: str) -> Tuple[Optional[List[str]], Optional[List[Tuple[int, int, int]]]]:
        """从任意字典中搜索 classes 和 palette 字段"""
        classes = None
        palette = None
        
        # 搜索所有包含 classes 的字典定义
        classes_patterns = [
            r'["\']?classes["\']?\s*[:=]\s*\[(.*?)\]',
            r'["\']?classes["\']?\s*[:=]\s*\((.*?)\)',
        ]
        
        for pattern in classes_patterns:
            for match in re.finditer(pattern, content, re.DOTALL):
                try:
                    parsed = self._parse_string_list(match.group(1))
                    if parsed and len(parsed) > 0:
                        classes = parsed
                        break
                except:
                    continue
            if classes:
                break
        
        # 搜索所有包含 palette 的字典定义
        palette_patterns = [
            r'["\']?palette["\']?\s*[:=]\s*(\[(?:[^\[\]]*\[[^\[\]]*\][^\[\]]*)*\])',
            r'["\']?palette["\']?\s*[:=]\s*(\((?:[^\(\)]*\([^\(\)]*\)[^\(\)]*)*\))',
            r'["\']?palette["\']?\s*[:=]\s*(\[(?:[^\[\]]*\([^\(\)]*\)[^\[\]]*)*\])',
        ]
        
        for pattern in palette_patterns:
            for match in re.finditer(pattern, content, re.DOTALL):
                try:
                    palette_str = match.group(1)
                    try:
                        result = ast.literal_eval(palette_str)
                        if isinstance(result, (list, tuple)):
                            parsed_palette = []
                            for item in result:
                                if isinstance(item, (list, tuple)) and len(item) == 3:
                                    parsed_palette.append((int(item[0]), int(item[1]), int(item[2])))
                            if parsed_palette and len(parsed_palette) > 0:
                                palette = parsed_palette
                                break
                    except:
                        parsed = self._parse_palette_list(palette_str)
                        if parsed and len(parsed) > 0:
                            palette = parsed
                            break
                except:
                    continue
            if palette:
                break
        
        return classes, palette
    
    def _extract_from_dataset_config(self, content: str) -> Tuple[Optional[List[str]], Optional[List[Tuple[int, int, int]]]]:
        """从 dataset 配置中提取类别和调色板"""
        dataset_patterns = [
            r'train_dataloader\s*=\s*dict\((.*?)\)',
            r'val_dataloader\s*=\s*dict\((.*?)\)',
            r'test_dataloader\s*=\s*dict\((.*?)\)',
            r'dataset\s*=\s*dict\((.*?)\)',
        ]
        
        for pattern in dataset_patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                dataset_content = match.group(1)
                classes, palette = self._extract_from_any_dict(dataset_content)
                if classes or palette:
                    return classes, palette
        
        return None, None
    
    def _parse_string_list(self, content: str) -> Optional[List[str]]:
        """解析字符串列表"""
        try:
            content = content.strip()
            strings = re.findall(r'["\']([^"\']+)["\']', content)
            
            if strings:
                return strings
            
            try:
                full_str = f'[{content}]'
                result = ast.literal_eval(full_str)
                if isinstance(result, (list, tuple)):
                    return [str(item) for item in result]
            except:
                pass
            
            return None
        except Exception:
            return None
    
    def _parse_palette_list(self, content: str) -> Optional[List[Tuple[int, int, int]]]:
        """解析调色板列表"""
        try:
            # 提取所有的数字三元组
            tuples = re.findall(r'[\[\(]\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*[\]\)]', content)
            
            if tuples:
                return [(int(r), int(g), int(b)) for r, g, b in tuples]
            
            try:
                full_str = f'[{content}]'
                result = ast.literal_eval(full_str)
                if isinstance(result, (list, tuple)):
                    palette = []
                    for item in result:
                        if isinstance(item, (list, tuple)) and len(item) == 3:
                            palette.append((int(item[0]), int(item[1]), int(item[2])))
                    if palette:
                        return palette
            except:
                pass
            
            try:
                result = ast.literal_eval(content)
                if isinstance(result, (list, tuple)):
                    palette = []
                    for item in result:
                        if isinstance(item, (list, tuple)) and len(item) == 3:
                            palette.append((int(item[0]), int(item[1]), int(item[2])))
                    if palette:
                        return palette
            except:
                pass
            
            return None
        except Exception:
            return None
    
    def _parse_model_info(self, content: str):
        """从配置文件内容中解析模型信息"""
        
        # 解析模型类型
        model_type_match = re.search(r"model\s*=\s*dict\([^)]*type\s*=\s*['\"]([^'\"]+)['\"]", content)
        if model_type_match:
            self.model_type = model_type_match.group(1)
        
        # 解析 backbone 类型
        backbone_match = re.search(r"backbone\s*=\s*dict\([^)]*type\s*=\s*['\"]([^'\"]+)['\"]", content)
        if backbone_match:
            self.backbone = backbone_match.group(1)
        
        # 解析类别数
        num_classes_match = re.search(r"num_classes\s*=\s*(\d+)", content)
        if num_classes_match:
            self.num_classes = int(num_classes_match.group(1))
        
        # 尝试从注释中提取模型名称
        comment_match = re.search(r"#\s*Model:\s*([^\n]+)", content)
        if comment_match:
            self.model_name = comment_match.group(1).strip()
            return
        
        # 从 _base_ 导入推断模型名称
        base_match = re.search(r"_base_\s*=\s*\[[^\]]*['\"]([^'\"]*models?[^'\"]*)['\"]", content)
        if base_match:
            base_path = base_match.group(1)
            self.model_name = self._extract_model_name_from_path(base_path)
            return
    
    def _infer_model_name_from_filename(self, config_path: str) -> str:
        """从文件名推断模型名称"""
        filename = os.path.basename(config_path)
        name = os.path.splitext(filename)[0]
        
        # 常见的模型名称模式
        patterns = [
            (r'segformer[_-]?b(\d)', lambda m: f'SegFormer-B{m.group(1)}'),
            (r'segformer[_-]?mit[_-]?b(\d)', lambda m: f'SegFormer-B{m.group(1)}'),
            (r'deeplabv3plus[_-]?r(\d+)', lambda m: f'DeepLabV3Plus-R{m.group(1)}'),
            (r'pspnet[_-]?r(\d+)', lambda m: f'PSPNet-R{m.group(1)}'),
            (r'unet[_-]?s(\d+)', lambda m: f'UNet-S{m.group(1)}'),
            (r'fcn[_-]?r(\d+)', lambda m: f'FCN-R{m.group(1)}'),
            (r'swin[_-]?(tiny|small|base|large)', lambda m: f'Swin-{m.group(1).capitalize()}'),
            (r'([a-zA-Z]+)[\d_-]+', lambda m: m.group(1).upper()),
        ]
        
        for pattern, formatter in patterns:
            match = re.search(pattern, name, re.IGNORECASE)
            if match:
                return formatter(match)
        
        return self._clean_filename(name)
    
    def _extract_model_name_from_path(self, path: str) -> str:
        """从路径中提取模型名称"""
        parts = path.replace('\\', '/').split('/')
        for part in reversed(parts):
            if 'model' in part.lower() or any(m in part.lower() for m in 
                ['segformer', 'deeplabv3', 'pspnet', 'unet', 'fcn', 'swin']):
                return self._clean_filename(part)
        return self._clean_filename(parts[-1])
    
    def _clean_filename(self, name: str) -> str:
        """清理文件名，使其更易读"""
        name = re.sub(r'[_-](config|cfg|model)$', '', name, flags=re.IGNORECASE)
        name = name.replace('_', ' ').replace('-', ' ')
        name = ' '.join(word.capitalize() for word in name.split())
        return name


def parse_mmseg_config(config_path: str) -> Dict[str, Any]:
    """
    便捷函数：解析 MMSegmentation 配置文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        包含模型信息的字典，即使解析失败也会返回默认值
    """
    try:
        parser = ConfigParser()
        classes, palette = parser.parse_config_file(config_path)
        model_name = parser.extract_model_name(config_path)
        model_type = parser.extract_model_type(config_path)
        
        return {
            'config_path': config_path,
            'model_name': model_name,
            'model_type': model_type,
            'classes': classes,
            'palette': palette
        }
    except Exception as e:
        print(f"配置文件解析失败: {e}")
        return {
            'config_path': config_path,
            'model_name': None,
            'model_type': None,
            'classes': None,
            'palette': None,
            'error': str(e)
        }