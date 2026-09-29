'''
Description: 根据PTH文件名进行可视化
Author: Napier
LastEditors: Napier
LastEditorTime: 2021-8-19
'''

import os
import re
import pyecharts.options as opts
from pyecharts.charts import Line
from pyecharts.globals import ThemeType

class TrainingLogVisualizer:
    def __init__(self, dir_path, ext='.pth'):
        """
        初始化可视化器
        :param dir_path: 包含权重文件的文件夹路径
        :param ext: 文件后缀，默认 .pth
        """
        self.root_path = dir_path
        self.ext = ext

    def parse_metrics(self, metric_names):
        """
        解析文件夹下的文件名，提取指标数据
        :param metric_names: 需要提取的指标名称列表 (不包含数值部分)
        :return: (epoch_list, metric_data_dict)
        """
        if not os.path.exists(self.root_path):
            print(f"Error: 路径不存在 {self.root_path}")
            return [], {}

        files = [f for f in os.listdir(self.root_path) if f.endswith(self.ext)]
        
        # 存储解析后的数据列表，每个元素是一个字典 {'Epoch': 10, 'Loss': 0.5, ...}
        parsed_records = []

        print(f"找到 {len(files)} 个文件，开始解析...")

        for file_name in files:
            # 使用正则表达式提取指标
            # 逻辑：匹配 指标名 + (可能有的数字/小数点/负号/科学计数法)
            record = {}
            is_valid_file = False
            
            # 1. 必须先提取 Epoch，作为排序依据
            # 正则解释：Epoch后面跟着数字
            epoch_match = re.search(r"Epoch(\d+)", file_name, re.IGNORECASE)
            if epoch_match:
                record['Epoch'] = int(epoch_match.group(1))
                is_valid_file = True
            else:
                # 如果文件名里没有 Epoch 信息，跳过该文件
                continue

            # 2. 提取其他指标
            for name in metric_names:
                if name == 'Epoch': continue
                
                # 构造正则：名称 + (数字，支持小数、负数、科学计数法)
                # 这里的正则假设指标名和数值紧挨着，或者由非数字字符分隔
                # 例如: Train_Loss0.5  或者 Train_Loss-0.5
                pattern = rf"{re.escape(name)}[-_:]?([+-]?\d*\.?\d+(?:[eE][-+]?\d+)?)"
                match = re.search(pattern, file_name)
                
                if match:
                    try:
                        record[name] = float(match.group(1))
                    except ValueError:
                        record[name] = None
                else:
                    # 如果该文件缺失某个指标，记为 None
                    record[name] = None
            
            if is_valid_file:
                parsed_records.append(record)

        # 3. 按 Epoch 排序
        parsed_records.sort(key=lambda x: x['Epoch'])

        # 4. 转换为绘图所需的 列式数据 (Dictionary of Lists)
        # 确保数据对齐
        result_dict = {name: [] for name in metric_names if name != 'Epoch'}
        epoch_list = []

        for record in parsed_records:
            epoch_list.append(record['Epoch'])
            for name in result_dict.keys():
                # 如果某个Epoch缺失数据，填充None，pyecharts会自动断开连线
                result_dict[name].append(record.get(name, None))

        return epoch_list, result_dict

    def render_chart(self, epoch_list, data_dict, title="Training Metrics", output_name="metrics_chart.html"):
        """
        绘制并保存图表
        """
        if not epoch_list:
            print("没有解析到有效数据，无法绘图。")
            return

        line = Line(init_opts=opts.InitOpts(
            theme=ThemeType.WALDEN, 
            width='95%', 
            height='700px',
            page_title=title
        ))

        # 设置 X 轴
        line.add_xaxis(epoch_list)

        # 设置 Y 轴数据
        for name, values in data_dict.items():
            # 过滤掉全空的指标
            if all(v is None for v in values):
                print(f"警告: 指标 {name} 没有提取到任何数据，将不予显示。")
                continue
            
            line.add_yaxis(
                series_name=name,
                y_axis=values,
                is_symbol_show=False, # 数据点太多时不显示小圆点
                is_smooth=True,       # 平滑曲线
                label_opts=opts.LabelOpts(is_show=False) # 不显示每个点的值，防遮挡
            )

        # 全局配置
        line.set_global_opts(
            title_opts=opts.TitleOpts(title=title, subtitle=f"Total Epochs: {len(epoch_list)}"),
            tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),
            toolbox_opts=opts.ToolboxOpts(feature={
                "saveAsImage": {},
                "dataZoom": {},
                "restore": {},
                "dataView": {}
            }),
            datazoom_opts=[
                opts.DataZoomOpts(range_start=0, range_end=100), # 底部滑动条
                opts.DataZoomOpts(type_="inside") # 鼠标滚轮缩放
            ],
            legend_opts=opts.LegendOpts(pos_top="5%")
        )

        # 保存路径
        save_path = os.path.join(self.root_path, output_name)
        line.render(save_path)
        print(f"图表已生成: {save_path}")

if __name__ == '__main__':
    import argparse
    from utils import hint_if_no_args

    hint_if_no_args(os.path.basename(__file__))

    DEFAULT_METRICS = [
        'Epoch',
        'Train_Loss', 'Val_Loss',
        'Train_f_score', 'Val_f_score',
        'Train_pre_loss', 'Val_pre_loss',
    ]

    parser = argparse.ArgumentParser(
        description=("根据权重文件名解析训练指标并绘图。"
                     "文件名示例：Epoch100-Train_Loss0.45-Val_f_score0.88.pth")
    )
    parser.add_argument('--log-dir', default=r'D:\Projects\python\water\logs\BiSeNetv2_water',
                        help='权重文件所在目录（DEMO 默认）')
    parser.add_argument('--file-ext', default='.pth',
                        help='权重文件后缀（默认 .pth）')
    parser.add_argument('--metrics', nargs='+', default=DEFAULT_METRICS,
                        help="要提取的指标名（须包含 'Epoch'）")
    parser.add_argument('--title', default='BiSeNetv2 Training Logs',
                        help='图表标题')
    args = parser.parse_args()

    viewer = TrainingLogVisualizer(args.log_dir, args.file_ext)
    epochs, metrics = viewer.parse_metrics(args.metrics)
    viewer.render_chart(
        epoch_list=epochs,
        data_dict=metrics,
        title=args.title,
    )