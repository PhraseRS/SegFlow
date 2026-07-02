import os
import sys
import uuid
from typing import Dict, List, Tuple

# Shapefile 标准 sidecar 后缀白名单（小写）
# 参考：ESRI Shapefile 技术文档 + QGIS/ArcGIS 实践
SHP_SIDECAR_EXTS = {
    '.shp', '.shx', '.dbf', '.prj', '.cpg',
    '.qmd', '.qix', '.sbn', '.sbx', '.shp.xml',
}
# GeoTIFF 标准 sidecar 后缀白名单
TIF_SIDECAR_EXTS = {
    '.tif', '.tiff', '.tfw', '.aux.xml', '.ovr', '.tif.aux.xml',
}


def _split_double_ext(filename: str) -> Tuple[str, str]:
    """
    支持双后缀（如 .shp.xml, .tif.aux.xml）的拆分。
    返回 (basename, ext)，ext 包含前导点且为小写。
    """
    lower = filename.lower()
    for double_ext in ('.shp.xml', '.tif.aux.xml', '.aux.xml'):
        if lower.endswith(double_ext):
            return filename[:-len(double_ext)], double_ext
    base, ext = os.path.splitext(filename)
    return base, ext.lower()


def parse_mapping_file(mapping_path: str) -> Dict[str, str]:
    """
    解析双列映射文件，每行格式：old_basename<sep>new_basename
    分隔符支持 TAB / 逗号 / 多个空格。
    忽略空行和以 # 开头的注释行。

    :return: {old_basename: new_basename}
    :raises ValueError: 若发现重复的 old 或 new
    """
    if not os.path.exists(mapping_path):
        raise FileNotFoundError(f"映射文件不存在: {mapping_path}")

    mapping: Dict[str, str] = {}
    new_names_seen: Dict[str, str] = {}  # 反向检查：new -> old

    with open(mapping_path, 'r', encoding='utf-8') as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue

            # 依次尝试 TAB、逗号、空格作为分隔符
            for sep in ('\t', ',', None):  # None 表示按任意空白分割
                parts = line.split(sep) if sep else line.split()
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) == 2:
                    break
            else:
                raise ValueError(
                    f"映射文件第 {line_no} 行格式错误，应为 'old<TAB|,|space>new': {raw!r}"
                )

            old, new = parts
            if old in mapping:
                raise ValueError(f"映射文件第 {line_no} 行：旧名 '{old}' 重复")
            if new in new_names_seen:
                raise ValueError(
                    f"映射文件第 {line_no} 行：新名 '{new}' 与第 "
                    f"'{new_names_seen[new]}' 行的映射冲突"
                )
            mapping[old] = new
            new_names_seen[new] = old

    return mapping


def find_related_files(folder: str, basename: str, whitelist: set) -> List[str]:
    """
    在 folder 中查找 basename 对应的所有 sidecar 文件（按白名单过滤）。
    返回完整路径列表。
    """
    related: List[str] = []
    for filename in os.listdir(folder):
        full_path = os.path.join(folder, filename)
        if not os.path.isfile(full_path):
            continue
        file_base, file_ext = _split_double_ext(filename)
        if file_base == basename and file_ext in whitelist:
            related.append(full_path)
    return related

def _rename_two_stage(folder: str, mapping: Dict[str, str], whitelist: set,
                      kind_label: str, dry_run: bool = False) -> Tuple[int, int]:
    """
    两阶段重命名：先全部 old -> __tmp_<uuid>__，再 tmp -> new。
    避免 "a -> b、b -> c" 这类链式覆盖造成数据丢失。

    :return: (success_count, fail_count)
    """
    # 1. 检查每个 old 是否能在目录下找到至少一个对应文件
    plans: List[Tuple[str, str, List[str]]] = []  # (old, new, [files])
    for old, new in mapping.items():
        files = find_related_files(folder, old, whitelist)
        if files:
            plans.append((old, new, files))

    if not plans:
        print(f"[{kind_label}] 未在目录中找到映射表里的任何文件，跳过。")
        return 0, 0

    # 2. 冲突检测：目标文件已存在且不在重命名计划中（即不会被腾出来）
    old_basenames = {old for old, _, _ in plans}
    for old, new, files in plans:
        for f in files:
            _, ext = _split_double_ext(os.path.basename(f))
            target = os.path.join(folder, new + ext)
            if os.path.exists(target) and new != old:
                # 如果目标基础名也在被重命名（即将被腾出），允许
                if new not in old_basenames:
                    print(f"[{kind_label}] [冲突] 目标文件已存在: {target}（来自 {old}{ext}）")
                    return 0, len(plans)

    print(f"[{kind_label}] 共 {len(plans)} 组待重命名，"
          f"涉及 {sum(len(f) for _, _, f in plans)} 个文件。"
          f"{' (DRY-RUN)' if dry_run else ''}")

    if dry_run:
        for old, new, files in plans:
            for f in files:
                _, ext = _split_double_ext(os.path.basename(f))
                print(f"  [dry-run] {os.path.basename(f)} -> {new}{ext}")
        return len(plans), 0

    # 3. 第一阶段：old -> tmp
    tmp_token = uuid.uuid4().hex[:8]
    stage1: List[Tuple[str, str, str]] = []  # (tmp_path, new_basename, ext)
    success = 0
    try:
        for old, new, files in plans:
            for src in files:
                _, ext = _split_double_ext(os.path.basename(src))
                tmp_name = f"__rn_{tmp_token}__{old}{ext}"
                tmp_path = os.path.join(folder, tmp_name)
                os.rename(src, tmp_path)
                stage1.append((tmp_path, new, ext))
    except OSError as e:
        print(f"[{kind_label}] [严重] 第一阶段失败，正在回滚: {e}")
        # 回滚已经改名的文件
        for tmp_path, _, ext in stage1:
            base = os.path.basename(tmp_path)
            # 解析出原始 old: __rn_<token>__<old><ext>
            prefix = f"__rn_{tmp_token}__"
            if base.startswith(prefix):
                old_name = base[len(prefix):]
                try:
                    os.rename(tmp_path, os.path.join(folder, old_name))
                except OSError:
                    pass
        return 0, len(plans)

    # 4. 第二阶段：tmp -> new
    fail = 0
    for tmp_path, new, ext in stage1:
        target = os.path.join(folder, new + ext)
        try:
            os.rename(tmp_path, target)
            print(f"[{kind_label}] {os.path.basename(tmp_path)} -> {new}{ext}")
            success += 1
        except OSError as e:
            print(f"[{kind_label}] [失败] {tmp_path} -> {target}: {e}")
            fail += 1

    return success, fail


def batch_rename_gis_files(mapping_path: str, target_folder: str,
                           kinds: Tuple[str, ...] = ('tif', 'shp'),
                           dry_run: bool = False) -> None:
    """
    根据双列映射文件批量重命名 GIS 文件（含 sidecar）。

    :param mapping_path: 映射文件路径，每行 'old_basename<TAB|,|space>new_basename'
    :param target_folder: 目标文件夹
    :param kinds: 要处理的文件类型，'tif' 和/或 'shp'
    :param dry_run: 仅打印计划，不实际重命名
    """
    if not os.path.exists(target_folder):
        print(f"错误: 目标文件夹不存在: {target_folder}")
        return

    try:
        mapping = parse_mapping_file(mapping_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"错误: {e}")
        return

    print(f"加载映射 {len(mapping)} 条；模式: {'DRY-RUN' if dry_run else 'REAL'}")

    if 'tif' in kinds:
        print("\n--- 处理 TIF 及其 sidecar ---")
        _rename_two_stage(target_folder, mapping, TIF_SIDECAR_EXTS, 'TIF', dry_run)

    if 'shp' in kinds:
        print("\n--- 处理 SHP 及其 sidecar ---")
        _rename_two_stage(target_folder, mapping, SHP_SIDECAR_EXTS, 'SHP', dry_run)


if __name__ == '__main__':
    import argparse
    from utils import hint_if_no_args

    hint_if_no_args(os.path.basename(__file__))

    parser = argparse.ArgumentParser(
        description=("批量重命名 GIS 文件（含 sidecar）。"
                     "映射文件每行格式：old_basename<TAB|,|space>new_basename。"
                     "默认 dry-run，安全预演确认后再加 --apply 真实执行。")
    )
    parser.add_argument('--mapping', default=r'E:\Samples-水体\chengdu-1024\rename_mapping.txt',
                        help='双列映射文件路径')
    parser.add_argument('--target', default=r'E:\Samples-水体\chengdu-1024\label-shp',
                        help='待重命名文件所在目录')
    parser.add_argument('--kinds', nargs='+', default=['tif', 'shp'],
                        choices=['tif', 'shp'],
                        help="要处理的类型，可多选（默认 tif shp）")
    parser.add_argument('--apply', action='store_true',
                        help='真实执行重命名；不传则 dry-run 仅预演')
    args = parser.parse_args()

    batch_rename_gis_files(
        mapping_path=args.mapping,
        target_folder=args.target,
        kinds=tuple(args.kinds),
        dry_run=not args.apply,
    )