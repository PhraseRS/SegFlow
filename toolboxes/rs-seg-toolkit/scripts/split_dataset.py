import os
import shutil
import random
from tqdm import tqdm

def copy_files_from_list(src_dir, list_txt_path, dst_dir, ext='.png'):
    """
    根据 txt 列表从源文件夹复制文件到目标文件夹
    :param src_dir: 源文件夹路径
    :param list_txt_path: 包含文件名的 txt 文件路径 (假设每行只是文件名，不含后缀)
    :param dst_dir: 目标保存路径
    :param ext: 文件后缀 (用于拼接源路径)
    """
    if not os.path.exists(list_txt_path):
        print(f"错误: 列表文件不存在 {list_txt_path}")
        return

    os.makedirs(dst_dir, exist_ok=True)

    with open(list_txt_path, 'r', encoding='utf-8') as f:
        # 过滤空行并去除首尾空白
        names = [line.strip() for line in f.readlines() if line.strip()]

    print(f"准备从 {src_dir} 复制 {len(names)} 个文件到 {dst_dir} ...")

    success_count = 0
    missing_count = 0

    for name in tqdm(names):
        # 假设 txt 里存的是 ID (如 '001')，需要拼上后缀 (如 '.png')
        # 如果 txt 里已经有后缀，请修改此处逻辑
        full_filename = name if name.endswith(ext) else name + ext
        
        src_path = os.path.join(src_dir, full_filename)
        dst_path = os.path.join(dst_dir, full_filename)

        if os.path.exists(src_path):
            try:
                shutil.copy2(src_path, dst_path) # copy2 保留文件元数据
                success_count += 1
            except Exception as e:
                print(f"复制失败: {name} - {e}")
        else:
            # print(f"文件丢失: {src_path}") # 太多时可注释掉
            missing_count += 1

    print(f"完成。成功: {success_count}, 丢失: {missing_count}")


def generate_file_list(src_dir, txt_save_path, target_ext='.png', shuffle=True, seed=42):
    """
    扫描文件夹，生成文件名列表 txt
    :param src_dir: 要扫描的文件夹
    :param txt_save_path: 保存 txt 的位置
    :param target_ext: 只扫描特定后缀的文件
    :param shuffle: 是否打乱顺序
    :param seed: 随机种子，保证每次打乱结果一致
    """
    if not os.path.exists(src_dir):
        print(f"错误: 源目录不存在 {src_dir}")
        return

    # 扫描文件
    files = []
    for f in os.listdir(src_dir):
        # 检查后缀 (忽略大小写)
        if f.lower().endswith(target_ext.lower()):
            # 获取不带后缀的文件名
            name_no_ext = os.path.splitext(f)[0]
            files.append(name_no_ext)

    print(f"扫描到 {len(files)} 个 {target_ext} 文件。")

    # 打乱顺序
    if shuffle:
        # 设定随机种子，保证每次打乱的结果是一样的
        random.seed(seed)
        random.shuffle(files)
        print(f"已使用随机种子 {seed} 打乱文件顺序。")

    # 写入文件
    # 自动创建父目录（仅在 txt_save_path 含目录部分时才创建，避免 makedirs("") 报错）
    parent_dir = os.path.dirname(txt_save_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    
    with open(txt_save_path, 'w', encoding='utf-8') as f:
        for name in files:
            f.write(name + "\n")
            
    print(f"列表已保存至: {txt_save_path}")


if __name__ == "__main__":
    # --- 配置区域 ---
    # 场景1：生成数据集索引 (train.txt / val.txt)
    IMG_DIR = r'D:\WorkSpace\mmsegmentation\Dataset\DJG\JPEGImages'
    TXT_OUTPUT = r'D:\WorkSpace\mmsegmentation\Dataset\DJG\JPEGImages\train_list.txt'
    EXT = '.png'
    
    # 1. 生成列表
    generate_file_list(IMG_DIR, TXT_OUTPUT, EXT, shuffle=True)

    # 场景2：根据列表提取小样本数据集 (例如从总库中提取验证集文件)
    # LIST_FILE = r'D:\WorkSpace\mmsegmentation\Dataset\DJG\JPEGImages\val_list.txt'
    # TARGET_DIR = r'E:\nets-dataset\water\val_images'
    
    # 2. 提取文件 (取消注释以运行)
    # copy_files_from_list(IMG_DIR, TXT_OUTPUT, TARGET_DIR, EXT)

    print("Done.")