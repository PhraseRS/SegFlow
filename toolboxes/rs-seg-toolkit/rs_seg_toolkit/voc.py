from __future__ import annotations

import json
import random
import shutil
from pathlib import Path
from typing import Callable

import cv2
import numpy as np


EventEmitter = Callable[[dict], None]


def _noop_emit(_event: dict) -> None:
    return None


def _split_exts(value: str) -> tuple[str, ...]:
    exts = []
    for item in value.split(","):
        item = item.strip().lower()
        if not item:
            continue
        if not item.startswith("."):
            item = "." + item
        exts.append(item)
    return tuple(dict.fromkeys(exts))


def _parse_splits(value: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for part in value.split(","):
        if not part.strip():
            continue
        if ":" not in part:
            raise ValueError(f"Invalid split item: {part!r}")
        name, ratio = part.split(":", 1)
        name = name.strip()
        result[name] = float(ratio)
    if not result:
        raise ValueError("At least one split is required")
    total = sum(result.values())
    if total <= 0:
        raise ValueError("Split ratio total must be positive")
    return {name: ratio / total for name, ratio in result.items()}


def _parse_mapping(value: str) -> dict[int, int]:
    if not value:
        return {}
    mapping: dict[int, int] = {}
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"Invalid class mapping item: {part!r}")
        old, new = part.split(":", 1)
        mapping[int(old.strip())] = int(new.strip())
    return mapping


def _scan_files(root: Path, exts: tuple[str, ...]) -> tuple[dict[str, Path], list[dict]]:
    found: dict[str, Path] = {}
    warnings = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in exts:
            continue
        stem = path.stem
        if stem in found:
            warnings.append({
                "code": "duplicate_stem",
                "sample": stem,
                "message": f"Duplicate stem {stem!r}; keeping {found[stem].name}",
            })
            continue
        found[stem] = path
    return found, warnings


def _read_image(path: Path, flags: int) -> np.ndarray | None:
    try:
        buffer = np.fromfile(str(path), dtype=np.uint8)
        if buffer.size == 0:
            return None
        return cv2.imdecode(buffer, flags)
    except Exception:
        return None


def _write_image(path: Path, image: np.ndarray) -> bool:
    ok, buffer = cv2.imencode(path.suffix, image)
    if not ok:
        return False
    buffer.tofile(str(path))
    return True


def _remap_label(label: np.ndarray, mapping: dict[int, int]) -> np.ndarray:
    out = np.zeros(label.shape[:2], dtype=np.uint8)
    source = label[..., 0] if label.ndim == 3 else label
    for old, new in mapping.items():
        if not 0 <= new <= 255:
            raise ValueError(f"Mapped class id out of uint8 range: {new}")
        out[source == old] = np.uint8(new)
    return out


def _copy_or_remap_label(src: Path, dst: Path, mapping: dict[int, int]) -> None:
    if mapping:
        label = _read_image(src, cv2.IMREAD_UNCHANGED)
        if label is None:
            raise ValueError(f"Cannot read label: {src}")
        remapped = _remap_label(label, mapping)
        if not _write_image(dst.with_suffix(".png"), remapped):
            raise ValueError(f"Cannot write label: {dst}")
        return
    shutil.copy2(src, dst)


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _assign_splits(stems: list[str], split_ratios: dict[str, float], seed: int) -> dict[str, list[str]]:
    shuffled = stems[:]
    random.Random(seed).shuffle(shuffled)
    total = len(shuffled)
    names = list(split_ratios)
    assigned: dict[str, list[str]] = {}
    start = 0
    for name in names[:-1]:
        count = int(total * split_ratios[name])
        assigned[name] = shuffled[start:start + count]
        start += count
    assigned[names[-1]] = shuffled[start:]
    return assigned


def build_voc_dataset(
    image_dir: str,
    label_dir: str,
    output_root: str,
    splits: str = "train:0.7,val:0.2,test:0.1",
    seed: int = 42,
    image_exts: str = ".jpg,.jpeg,.png,.tif,.tiff,.bmp",
    label_exts: str = ".png,.tif,.tiff,.bmp",
    class_mapping: str = "",
    overwrite: bool = False,
    validate_after_build: bool = True,
    emit: EventEmitter = _noop_emit,
) -> dict:
    emit({"type": "started", "tool": "voc.build"})
    image_root = Path(image_dir)
    label_root = Path(label_dir)
    out_root = Path(output_root)
    if not image_root.is_dir():
        raise ValueError(f"Image directory not found: {image_root}")
    if not label_root.is_dir():
        raise ValueError(f"Label directory not found: {label_root}")
    if out_root.exists() and any(out_root.iterdir()) and not overwrite:
        raise ValueError(f"Output directory is not empty: {out_root}")

    image_files, warnings = _scan_files(image_root, _split_exts(image_exts))
    label_files, label_warnings = _scan_files(label_root, _split_exts(label_exts))
    warnings.extend(label_warnings)

    common = sorted(set(image_files) & set(label_files))
    missing_labels = sorted(set(image_files) - set(label_files))
    missing_images = sorted(set(label_files) - set(image_files))
    for stem in missing_labels:
        warnings.append({"code": "missing_label", "sample": stem})
    for stem in missing_images:
        warnings.append({"code": "missing_image", "sample": stem})
    if not common:
        raise ValueError("No paired image/label samples found")

    mapping = _parse_mapping(class_mapping)
    jpeg_dir = out_root / "JPEGImages"
    seg_dir = out_root / "SegmentationClass"
    split_dir = out_root / "ImageSets" / "Segmentation"
    jpeg_dir.mkdir(parents=True, exist_ok=True)
    seg_dir.mkdir(parents=True, exist_ok=True)
    split_dir.mkdir(parents=True, exist_ok=True)

    total = len(common)
    copied = []
    errors = []
    class_ids: set[int] = set()
    for index, stem in enumerate(common, start=1):
        emit({"type": "progress", "current": index, "total": total, "message": f"Copying {stem}"})
        image_src = image_files[stem]
        label_src = label_files[stem]
        image_dst = jpeg_dir / image_src.name
        label_dst = seg_dir / (f"{stem}.png" if mapping else label_src.name)
        try:
            shutil.copy2(image_src, image_dst)
            _copy_or_remap_label(label_src, label_dst, mapping)
            label = _read_image(label_dst, cv2.IMREAD_UNCHANGED)
            if label is not None:
                if label.ndim == 3:
                    errors.append({"code": "color_label", "sample": stem, "message": "Label is multi-channel"})
                else:
                    unique = np.unique(label)
                    class_ids.update(int(v) for v in unique.tolist())
            copied.append(stem)
        except Exception as exc:
            errors.append({"code": "copy_failed", "sample": stem, "message": str(exc)})

    assigned = _assign_splits(copied, _parse_splits(splits), seed)
    for split, stems in assigned.items():
        (split_dir / f"{split}.txt").write_text(
            "".join(f"{stem}\n" for stem in stems),
            encoding="utf-8",
        )

    classes = sorted(class_ids)
    _write_json(out_root / "classes.json", {
        "classes": [{"id": class_id, "name": f"class_{class_id}"} for class_id in classes],
        "source": "rs-seg-toolkit voc.build",
    })

    status = "success" if not errors else "failed"
    report = {
        "tool": "voc.build",
        "status": status,
        "output_root": str(out_root),
        "samples": {
            "matched": len(common),
            "copied": len(copied),
            "skipped": len(missing_labels) + len(missing_images) + len(errors),
            **{split: len(stems) for split, stems in assigned.items()},
        },
        "warnings": warnings,
        "errors": errors,
    }

    if validate_after_build and status == "success":
        validation = validate_voc_dataset(str(out_root), emit=_noop_emit)
        report["validation"] = validation
        if validation.get("status") != "success":
            report["status"] = "failed"
            status = "failed"

    _write_json(out_root / "toolkit_report.json", report)
    emit({"type": "result", "status": status, "output_root": str(out_root), "report": report})
    return report


def _find_existing(root: Path, stem: str, exts: tuple[str, ...]) -> Path | None:
    for ext in exts:
        candidate = root / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def validate_voc_dataset(
    dataset_root: str,
    max_class_id: int = 255,
    emit: EventEmitter = _noop_emit,
) -> dict:
    emit({"type": "started", "tool": "voc.validate"})
    root = Path(dataset_root)
    image_dir = root / "JPEGImages"
    label_dir = root / "SegmentationClass"
    split_dir = root / "ImageSets" / "Segmentation"
    errors = []
    warnings = []

    for path, code in ((image_dir, "missing_images_dir"), (label_dir, "missing_labels_dir"), (split_dir, "missing_split_dir")):
        if not path.is_dir():
            errors.append({"code": code, "path": str(path)})

    if errors:
        report = {"tool": "voc.validate", "status": "failed", "errors": errors, "warnings": warnings}
        emit({"type": "result", "status": "failed", "report": report})
        return report

    image_exts = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")
    label_exts = (".png", ".tif", ".tiff", ".bmp")
    sample_ids: list[str] = []
    for split in ("train", "val", "test"):
        split_file = split_dir / f"{split}.txt"
        if not split_file.is_file():
            warnings.append({"code": "missing_split_file", "split": split})
            continue
        for line in split_file.read_text(encoding="utf-8").splitlines():
            sample = line.strip()
            if sample:
                sample_ids.append(sample)

    for index, sample in enumerate(sample_ids, start=1):
        emit({"type": "progress", "current": index, "total": len(sample_ids), "message": f"Validating {sample}"})
        image_path = _find_existing(image_dir, sample, image_exts)
        label_path = _find_existing(label_dir, sample, label_exts)
        if image_path is None:
            errors.append({"code": "missing_image", "sample": sample})
            continue
        if label_path is None:
            errors.append({"code": "missing_label", "sample": sample})
            continue

        image = _read_image(image_path, cv2.IMREAD_UNCHANGED)
        label = _read_image(label_path, cv2.IMREAD_UNCHANGED)
        if image is None:
            errors.append({"code": "corrupt_image", "sample": sample, "path": str(image_path)})
            continue
        if label is None:
            errors.append({"code": "corrupt_label", "sample": sample, "path": str(label_path)})
            continue
        if label.ndim == 3:
            errors.append({"code": "color_label", "sample": sample})
            continue
        if image.shape[:2] != label.shape[:2]:
            errors.append({
                "code": "dimension_mismatch",
                "sample": sample,
                "image_shape": list(image.shape[:2]),
                "label_shape": list(label.shape[:2]),
            })
        if int(label.max()) > max_class_id:
            errors.append({"code": "class_id_out_of_range", "sample": sample, "max_value": int(label.max())})

    status = "success" if not errors else "failed"
    report = {
        "tool": "voc.validate",
        "status": status,
        "samples": {"checked": len(sample_ids)},
        "warnings": warnings,
        "errors": errors,
    }
    emit({"type": "result", "status": status, "report": report})
    return report
