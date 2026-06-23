# SegFlow

A graphical workspace for remote-sensing semantic segmentation. It provides an integrated visual workflow for dataset management, sample analysis, configuration generation, model training, model evaluation, project-state restoration, and large-image inference, powered by [OpenMMLab / MMSegmentation](https://github.com/open-mmlab/mmsegmentation).

---

## ✨ Key Features

- **Dataset Management**: Import VOC-style datasets, browse samples, lazily load thumbnails, and resplit datasets
- **Sample Analysis**: Class-distribution statistics, coverage analysis, metadata inspection, and dataset health checks
- **Visualization Canvas**: `rasterio`-based GeoTIFF pyramid/LOD loading, multiband display, and pseudocolor mask overlays
- **Training Configuration**: Visual hyperparameter editing, Advisor recommendations, pretrained-weight selection, and one-click MMSeg config generation
- **Model Training**: Run training through a selected conda environment, parse logs in real time, plot loss/metric curves, save checkpoints, and preview live predictions
- **Model Testing**: Evaluate trained checkpoints through the MMSegmentation test runner and display overall and per-class metrics
- **Project Files**: Save and reopen dataset, model, inference, task configuration, UI state, and generated custom-module paths with `.rsgproj` files
- **Large-Image Inference**: GDAL-based block and sliding-window inference for large remote-sensing images, with progress reported through Qt signals

---

## 🧱 Two-Layer Environment Design (Important)

> SegFlow intentionally separates its dependencies into **two independent environments**. Please understand this design before installation.

| Layer | Purpose | Installation | Required |
|------|------|---------|---------|
| **Layer A: GUI Host Environment** | Runs the desktop application, dataset tools, visualization, and config generation | `pip install -r requirements.txt` | Yes |
| **Layer B: Training/Runtime Environment** | Provides PyTorch, MMEngine, MMCV, and MMSegmentation for training, model testing, and real inference | Separate conda environment (`environment_train.yml`) | Required for training, testing, and real inference |

The two layers communicate through **isolated subprocesses**. The GUI does not require the training framework to be installed in its own environment. Select a configured runtime Python interpreter in the **Environment Configuration** panel to use it for training, testing, and inference.

Generated modules such as `custom_rs_dataset.py` and `custom_live_pred_hook.py` are recorded in the project file and loaded explicitly from their file paths during testing and inference.

For a detailed dependency analysis, see [`docs/ENVIRONMENT_REQUIREMENTS.md`](docs/ENVIRONMENT_REQUIREMENTS.md).

---

## 🚀 Quick Installation

### Option 1: Installation Script (Recommended)

**Windows:**
```bat
install.bat
```

**Linux / macOS:**
```bash
chmod +x install.sh
./install.sh
```

The scripts install the GUI dependencies, create the conda training/runtime environment defined by `environment_train.yml`, and install GPU-enabled PyTorch, MMCV, and MMSegmentation. CUDA and torch tags can be specified explicitly (defaults: `cu118` / `torch2.1`):

```bat
REM Windows: use CUDA 12.1
install.bat cu121 torch2.1
```
```bash
# Linux / macOS: use CUDA 12.1
./install.sh cu121 torch2.1
```

> ⚠️ The training/runtime environment requires an NVIDIA driver compatible with the selected CUDA build.

### Option 2: Manual Installation

```bash
# Layer A: GUI host environment
pip install -r requirements.txt

# Layer B: training/testing/inference environment
conda env create -f environment_train.yml
conda activate gui-mmseg
# Install a GPU-enabled PyTorch build (CUDA 11.8 example)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
# Install the matching MMCV build
pip install mmcv==2.1.0 -f https://download.openmmlab.com/mmcv/dist/cu118/torch2.1/index.html
# Install MMEngine and MMSegmentation
pip install mmengine "mmsegmentation>=1.0.0,<2.0.0"
```

> Replace `cu118` / `torch2.1` with versions compatible with your system and PyTorch build.

---

## ▶️ Launch

```bash
python main.py
```

Dataset management and visualization are available after startup. Before training, model testing, or real inference, select and validate the runtime Python interpreter in the **Environment Configuration** panel.

Use **File > Save Project** to create an `.rsgproj` file and **File > Open Project** to restore the saved dataset, model, custom modules, task settings, inference settings, and last active tab.

---

## ⚙️ Environment Notes

Please note the following before installation and use:

| Item | Description |
|------|------|
| **Two-environment design** | The GUI host and training/runtime environments can be separate. Select the configured runtime interpreter in the GUI when training, testing, or running real inference. |
| **Runtime interpreter** | The selected interpreter must contain compatible versions of PyTorch, MMEngine, MMCV, and MMSegmentation. Selecting the base Anaconda interpreter may cause `No module named 'mmengine'`. |
| **Conda is optional for the GUI** | The GUI can start without conda, with environment-discovery features degraded. A configured runtime environment is required for framework-backed operations. |
| **GPU requirements** | Training and real inference normally require a compatible NVIDIA driver and CUDA-enabled PyTorch build. Dataset management and visualization can run without a GPU. |
| **Custom modules** | Testing and inference load generated custom modules from paths stored in the `.rsgproj` file instead of adding their directories to `PYTHONPATH`. |
| **Rasterio recommended** | Without `rasterio`, the application can start, but multiband GeoTIFF display and pyramid/LOD support are unavailable or degraded. |
| **Python version** | Python 3.9 or 3.10 is recommended. The OpenMMLab ecosystem may lag behind newer Python versions such as 3.12+. |

---

## 📖 Related Documentation

- [Environment Requirements](docs/ENVIRONMENT_REQUIREMENTS.md) — Dependency layers, optimization analysis, and release recommendations
