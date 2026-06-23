<p align="center">
  <strong>English</strong> | <a href="ENVIRONMENT_REQUIREMENTS_zh-CN.md">简体中文</a>
</p>

# SegFlow Runtime Environment Requirements

> This document analyzes the project's minimum runtime environment, dependency layers, possible optimizations, and recommended environment-management practices for open-source distribution.

---

## 1. Dependency Architecture

SegFlow uses two independent dependency layers. The layers communicate through isolated subprocesses, allowing the GUI host and model runtime to use different Python environments.

```text
┌────────────────────────────────────────────────────────────┐
│                    Layer A: GUI Host                       │
│  Required by the desktop application                      │
│                                                            │
│  PySide6 · NumPy · OpenCV · Pillow · Matplotlib           │
│  rasterio (optional but strongly recommended)              │
└──────────────────────────┬─────────────────────────────────┘
                           │ isolated subprocess
┌──────────────────────────▼─────────────────────────────────┐
│              Layer B: Training/Inference Runtime           │
│  Selected by the user in the Environment panel            │
│                                                            │
│  PyTorch · MMCV · MMEngine · MMSegmentation               │
│  GDAL (osgeo) · CUDA runtime                              │
└────────────────────────────────────────────────────────────┘
```

---

## 2. Layer A: GUI Host Dependencies

### 2.1 Required dependencies

| Package | Purpose | Main references |
|---|---|---|
| `PySide6` | GUI widgets, signals, threads, images, and drawing | Entire project |
| `numpy` | Image arrays, mask calculations, and sample statistics | `smart_canvas`, `mask_renderer`, `inference_engine`, `skills/` |
| `opencv-python` (`cv2`) | Image I/O, resizing, and color-space conversion | `smart_canvas`, `mask_renderer`, `inference_engine` |
| `Pillow` (`PIL`) | Large-image access and PNG/JPEG reading | `inference_engine` |
| `matplotlib` | Class-distribution charts and statistical plots | `class_distribution_widget` |
| `jinja2` | Generated MMSegmentation configuration templates | `core/logic_engine.py` |

### 2.2 Optional but strongly recommended dependencies

| Package | Purpose | Effect when missing |
|---|---|---|
| `rasterio` | Multiband GeoTIFF access, image pyramids/LOD, and viewport windows | `.tif` display falls back to limited OpenCV handling |
| `pyqtgraph` | Real-time loss, mIoU, and mAcc plots | Live training charts are unavailable |
| `qtawesome` | Toolbar and panel icons | Text or native UI fallbacks are used |

### 2.3 Python standard library

No separate installation is required for modules such as:

`os`, `sys`, `re`, `json`, `sqlite3`, `subprocess`, `multiprocessing`, `hashlib`, `math`, `csv`, `ast`, `copy`, `time`, `signal`, `datetime`, `pathlib`, `dataclasses`, `enum`, `typing`, `abc`, and `collections`.

---

## 3. Layer B: Training and Inference Dependencies

> Select this independent environment in the application's Environment Configuration panel. It does not need to be merged with the GUI host environment.

### 3.1 Core model-runtime dependencies

| Package | Version constraint | Purpose |
|---|---|---|
| `torch` (PyTorch) | `>=2.0` recommended | Tensor computation and GPU execution |
| `torchvision` | Match the PyTorch build | Vision components and ecosystem compatibility |
| `mmengine` | `>=0.7.0` | OpenMMLab configuration, runners, and hooks |
| `mmcv` | `>=2.0.0` | OpenMMLab operators and model components |
| `mmsegmentation` | `>=1.0.0,<2.0.0` | Semantic-segmentation framework |
| NVIDIA driver/CUDA runtime | Match the PyTorch build | GPU-accelerated training and inference |

### 3.2 Large-image inference extension

| Package | Purpose | Effect when missing |
|---|---|---|
| `gdal` (`osgeo`) | Tiled reading of large rasters and georeferenced GeoTIFF output | Large-image tiled inference is unavailable |

---

## 4. Dependency Design Notes

### 4.1 Matplotlib and PyQtGraph

Matplotlib is used for class-distribution visualization, while PyQtGraph provides efficient real-time training plots. Keeping their responsibilities separate avoids forcing the statistical charts and live plots into one rendering stack.

### 4.2 Progress reporting without `tqdm`

Inference progress is delivered through:

```text
InferenceEngine callback → worker progress signal → QProgressBar
```

This keeps progress reporting inside the Qt signal/slot architecture rather than writing terminal progress to standard output.

### 4.3 Rasterio and GDAL

Both libraries support GeoTIFF, but they serve different layers:

- Layer A uses Rasterio for Python-friendly display, multiband reading, and viewport windows.
- Layer B uses GDAL for robust tiled inference and georeferenced output.

The current separation should be retained.

### 4.4 Pillow and OpenCV

Pillow is useful for lazy image access and large-image cropping. OpenCV handles BGR-oriented operations, resizing, and mask processing. Their current division of responsibility is intentional.

### 4.5 Hidden system dependencies

| Dependency | Source | Risk |
|---|---|---|
| `sqlite3` | Dataset metadata cache | Usually bundled with Python, but may be absent from minimal distributions |
| `conda` | Runtime environment discovery | Environment listing is limited when only venv/pyenv is available |
| System fonts/display server | Qt initialization | Headless Linux systems may require additional Qt platform configuration |

---

## 5. Minimum Installation

### 5.1 Layer A: GUI host

Python 3.9 or 3.10 is recommended.

```bash
pip install -r requirements.txt
pip install Jinja2 pyqtgraph qtawesome
```

Equivalent core packages:

```bash
pip install PySide6 numpy opencv-python Pillow matplotlib rasterio
```

### 5.2 Layer B: training and inference

```bash
# 1. Create an isolated environment
conda create -n gui-mmseg python=3.9 -y
conda activate gui-mmseg

# 2. Install a PyTorch build matching the local NVIDIA driver
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# 3. Install OpenMMLab components
pip install mmengine
pip install mmcv==2.1.0 -f https://download.openmmlab.com/mmcv/dist/cu118/torch2.1/index.html
pip install "mmsegmentation>=1.0.0,<2.0.0"

# 4. Install GDAL for large-image inference
conda install gdal -c conda-forge
```

Replace `cu118` and `torch2.1` with mutually compatible versions for the target system.

---

## 6. Environment Management for Distribution

### 6.1 Recommended file layout

```text
SegFlow/
├── requirements.txt
└── environment_train.yml
```

- `requirements.txt` describes the GUI host.
- `environment_train.yml` creates the isolated model runtime.

### 6.2 Points that should remain explicit

| Topic | Requirement |
|---|---|
| Two-environment design | The GUI and model runtime are separate; select the runtime interpreter in the GUI |
| Conda | Not mandatory for basic GUI use, but recommended for the GPU/OpenMMLab runtime |
| GPU | Data management can run without a GPU; training and accelerated inference require a compatible NVIDIA setup |
| Rasterio | Strongly recommended for correct large `.tif` display |
| Python | Python 3.9 or 3.10 is the recommended compatibility range |

### 6.3 Distribution priority

1. Source code with `requirements.txt` and `environment_train.yml`.
2. One-click installation scripts (`install.bat` and `install.sh`).
3. A frozen executable only when there is a clear need; bundling the complete GPU framework is large and difficult to maintain.

For this project, source distribution with layered dependencies and installation scripts is the preferred approach.

---

## 7. Python Compatibility

| Python version | Status | Notes |
|---|---|---|
| 3.8 | ⚠️ Not recommended | Current PySide6 versions no longer target Python 3.8 |
| 3.9 | ✅ Recommended | Best match for the current environment files |
| 3.10 | ✅ Supported | Commonly used by MMSegmentation installations |
| 3.11 | ⚠️ Verify | Core packages support it, but OpenMMLab/CUDA combinations must be checked |
| 3.12/3.13 | ⚠️ Use caution | New Python releases may not be supported by all OpenMMLab binary packages |

**Officially supporting Python 3.9 and 3.10 is recommended.**

---

*This document is based on static source and environment-file analysis. Validate exact package, CUDA, and driver combinations on the target machine.*
