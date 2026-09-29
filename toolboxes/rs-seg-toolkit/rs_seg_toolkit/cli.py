from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

from rs_seg_toolkit import __version__


TOOLBOX_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = TOOLBOX_ROOT / "scripts"


def emit(event: dict) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def _run_script(args: argparse.Namespace, extra_args: list[str]) -> int:
    script_path = SCRIPTS_DIR / args.script
    if not script_path.is_file():
        emit({"type": "error", "message": f"Script not found: {args.script}"})
        return 2

    sys.path.insert(0, str(TOOLBOX_ROOT))
    sys.argv = [str(script_path), *extra_args]
    emit({"type": "started", "tool": f"script.{args.script}"})
    try:
        runpy.run_path(str(script_path), run_name="__main__")
    except SystemExit as exc:
        code = int(exc.code or 0)
        status = "success" if code == 0 else "failed"
        emit({"type": "result", "status": status, "exit_code": code})
        return code
    emit({"type": "result", "status": "success", "exit_code": 0})
    return 0


def _append_option(args: list[str], flag: str, value: object) -> None:
    if value is None or str(value).strip() == "":
        return
    args.extend([flag, str(value)])


def _append_common_clip_args(script_args: list[str], args: argparse.Namespace) -> None:
    _append_option(script_args, "--crop-size", args.crop_size)
    _append_option(script_args, "--overlap-ratio", args.overlap_ratio)
    _append_option(script_args, "--edge-policy", args.edge_policy)
    _append_option(script_args, "--small-image", args.small_image)
    _append_option(script_args, "--band-order", args.band_order)
    _append_option(script_args, "--dst-ext", args.dst_ext)
    _append_option(script_args, "--nodata-value", args.nodata_value)
    _append_option(script_args, "--min-valid-ratio", args.min_valid_ratio)
    if args.bgr_swap:
        script_args.append("--bgr-swap")


def _run_clip(args: argparse.Namespace) -> int:
    script_args: list[str] = []
    if args.mode == "paired":
        missing = [
            label
            for label, value in (
                ("--src-image", args.src_image),
                ("--src-label", args.src_label),
                ("--dst-image", args.dst_image),
                ("--dst-label", args.dst_label),
            )
            if not value
        ]
        if missing:
            emit({"type": "error", "message": f"Missing paired clip parameter(s): {', '.join(missing)}"})
            return 2
        _append_option(script_args, "--src-image", args.src_image)
        _append_option(script_args, "--src-label", args.src_label)
        _append_option(script_args, "--dst-image", args.dst_image)
        _append_option(script_args, "--dst-label", args.dst_label)
        _append_common_clip_args(script_args, args)
        _append_option(script_args, "--label-dst-ext", args.label_dst_ext)
        _append_option(script_args, "--min-foreground-ratio", args.min_foreground_ratio)
        _append_option(script_args, "--label-ignore-value", args.label_ignore_value)
    else:
        missing = [
            label
            for label, value in (
                ("--src", args.src),
                ("--dst", args.dst),
            )
            if not value
        ]
        if missing:
            emit({"type": "error", "message": f"Missing single clip parameter(s): {', '.join(missing)}"})
            return 2
        _append_option(script_args, "--src", args.src)
        _append_option(script_args, "--dst", args.dst)
        _append_common_clip_args(script_args, args)

    return _run_script(argparse.Namespace(script="clip_image.py"), script_args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rsseg-toolkit")
    parser.add_argument("--version", action="version", version=f"rs-seg-toolkit {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    voc_parser = subparsers.add_parser("voc", help="VOC dataset tools")
    voc_sub = voc_parser.add_subparsers(dest="voc_command", required=True)

    build = voc_sub.add_parser("build", help="Build a VOC dataset")
    build.add_argument("--image-dir", required=True)
    build.add_argument("--label-dir", required=True)
    build.add_argument("--output-root", required=True)
    build.add_argument("--splits", default="train:0.7,val:0.2,test:0.1")
    build.add_argument("--seed", type=int, default=42)
    build.add_argument("--image-exts", default=".jpg,.jpeg,.png,.tif,.tiff,.bmp")
    build.add_argument("--label-exts", default=".png,.tif,.tiff,.bmp")
    build.add_argument("--class-mapping", default="")
    build.add_argument("--overwrite", action="store_true")
    build.add_argument("--no-validate", action="store_true")

    validate = voc_sub.add_parser("validate", help="Validate a VOC dataset")
    validate.add_argument("--dataset-root", required=True)
    validate.add_argument("--max-class-id", type=int, default=255)

    clip = subparsers.add_parser("clip", help="Clip single rasters or paired image/label rasters")
    clip.add_argument("--mode", choices=("paired", "single"), default="paired")
    clip.add_argument("--src")
    clip.add_argument("--dst")
    clip.add_argument("--src-image")
    clip.add_argument("--src-label")
    clip.add_argument("--dst-image")
    clip.add_argument("--dst-label")
    clip.add_argument("--crop-size", type=int, default=1024)
    clip.add_argument("--overlap-ratio", type=float, default=0.0)
    clip.add_argument("--edge-policy", choices=("append", "drop", "pad"), default="drop")
    clip.add_argument("--small-image", choices=("skip", "pad"), default="skip")
    clip.add_argument("--band-order", choices=("auto", "bgr", "keep", "rgb"), default="auto")
    clip.add_argument("--dst-ext", default="auto")
    clip.add_argument("--label-dst-ext", default="auto")
    clip.add_argument("--nodata-value", default="")
    clip.add_argument("--min-valid-ratio", type=float, default=0.0)
    clip.add_argument("--min-foreground-ratio", type=float, default=0.0)
    clip.add_argument("--label-ignore-value", type=int, default=0)
    clip.add_argument("--bgr-swap", action="store_true")

    script = subparsers.add_parser("script", help="Run a legacy toolkit script")
    script.add_argument("script")

    subparsers.add_parser("list", help="List available legacy scripts")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] == "script":
        known, extra = parser.parse_known_args(argv)
    else:
        known = parser.parse_args(argv)
        extra = []

    if known.command == "list":
        scripts = sorted(path.name for path in SCRIPTS_DIR.glob("*.py"))
        emit({"type": "result", "status": "success", "scripts": scripts})
        return 0

    if known.command == "script":
        return _run_script(known, extra)

    if known.command == "clip":
        return _run_clip(known)

    if known.command == "voc" and known.voc_command == "build":
        from rs_seg_toolkit.voc import build_voc_dataset

        try:
            result = build_voc_dataset(
                image_dir=known.image_dir,
                label_dir=known.label_dir,
                output_root=known.output_root,
                splits=known.splits,
                seed=known.seed,
                image_exts=known.image_exts,
                label_exts=known.label_exts,
                class_mapping=known.class_mapping,
                overwrite=known.overwrite,
                validate_after_build=not known.no_validate,
                emit=emit,
            )
        except Exception as exc:
            emit({"type": "error", "message": str(exc)})
            return 1
        return 0 if result.get("status") == "success" else 1

    if known.command == "voc" and known.voc_command == "validate":
        from rs_seg_toolkit.voc import validate_voc_dataset

        result = validate_voc_dataset(
            dataset_root=known.dataset_root,
            max_class_id=known.max_class_id,
            emit=emit,
        )
        return 0 if result.get("status") == "success" else 1

    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
