import os
import shutil
from tqdm import tqdm

def batch_change_extension(src_dir, old_ext='.png', new_ext='.tif', dst_dir=None):
    """
    批量修改文件后缀名（可选择是否复制到新目录）
    注意：这仅是重命名，不会进行文件格式编码转换！
    
    :param src_dir: 源文件夹路径
    :param old_ext: 旧后缀 (如 .png)
    :param new_ext: 新后缀 (如 .tif)
    :param dst_dir: (可选) 目标文件夹路径。如果为None，则在源文件夹原地修改。
    """
    
    # 规范化后缀格式（确保有点）
    if not old_ext.startswith('.'): old_ext = '.' + old_ext
    if not new_ext.startswith('.'): new_ext = '.' + new_ext

    if not os.path.exists(src_dir):
        print(f"源路径不存在: {src_dir}")
        return

    # 获取需处理的文件列表
    files = [f for f in os.listdir(src_dir) if f.endswith(old_ext)]
    
    if not files:
        print(f"在 {src_dir} 中未找到 {old_ext} 文件。")
        return

    # 模式判断
    is_copy_mode = dst_dir is not None
    
    if is_copy_mode:
        os.makedirs(dst_dir, exist_ok=True)
        print(f"模式: 复制并重命名 -> {dst_dir}")
    else:
        print(f"模式: 原地重命名 -> {src_dir}")

    print(f"发现 {len(files)} 个文件，准备处理...")

    success_count = 0
    
    for filename in tqdm(files):
        try:
            # 构建源文件完整路径
            src_file_path = os.path.join(src_dir, filename)
            
            # 构建新文件名 (例如: image.png -> image.tif)
            # 使用 splitext 防止文件名中间也有 .png
            base_name = os.path.splitext(filename)[0]
            new_filename = base_name + new_ext
            
            if is_copy_mode:
                # 复制模式：将源文件复制到目标目录，并直接使用新名字
                dst_file_path = os.path.join(dst_dir, new_filename)
                
                # copy2 保留文件元数据（时间戳等）
                shutil.copy2(src_file_path, dst_file_path)
            else:
                # 原地模式：直接重命名
                dst_file_path = os.path.join(src_dir, new_filename)
                os.rename(src_file_path, dst_file_path)
            
            success_count += 1
            
        except Exception as e:
            print(f"处理文件 {filename} 时出错: {e}")

    print(f"处理完成。成功: {success_count}/{len(files)}")
    if old_ext.lower() == '.png' and new_ext.lower() in ['.tif', '.tiff']:
        print("\n[警告] 你将 .png 后缀改为了 .tif，但没有转换图像编码！")
        print("       如果后续软件无法打开，请使用 convert_png_to_geotiff.py 进行真正的格式转换。")

if __name__ == '__main__':
    import argparse
    from utils import hint_if_no_args

    hint_if_no_args(os.path.basename(__file__))

    parser = argparse.ArgumentParser(
        description="批量修改文件后缀名（仅重命名，不做格式转换）。无参时使用内置 DEMO 默认值。"
    )
    parser.add_argument('--src', default=r'C:\Users\xi\Desktop\test\04\1024',
                        help='源文件夹路径（DEMO 默认）')
    parser.add_argument('--dst', default=r'C:\Users\xi\Desktop\test\04\1024tif',
                        help='目标文件夹路径；省略或传空字符串则在源目录原地改名')
    parser.add_argument('--old-ext', default='.png', help='旧后缀（默认 .png）')
    parser.add_argument('--new-ext', default='.tif', help='新后缀（默认 .tif）')
    args = parser.parse_args()

    batch_change_extension(
        src_dir=args.src,
        old_ext=args.old_ext,
        new_ext=args.new_ext,
        dst_dir=args.dst if args.dst else None,
    )