# Separable Gamma CFAR And Neuron Review Workbench

A toolkit for scientific calcium/voltage-imaging videos. The repository now has
two complementary workflows:

- a Python grid-search pipeline for Gamma/Kalman-MCC filtering, CFAR detection,
  and report generation
- a Fiji/Groovy plus browser workbench workflow for neuron ROI review, trace
  denoising, event annotation, and user-guided parameter iteration

---

## Features

* **Interchangeable pre-processing filters for grid search**

  * **Gamma ST filter** (spatio-temporal enhancement)
  * **Kalman–MCC** (robust background estimation via maximum correntropy)
* **Parallel grid search** across filter & detector parameters
* **Evaluation & selection**

  * FROC (TPR vs FPPI), truncated AUC, Youden’s J (balanced operating point)
  * Top-K and balanced model summaries
* **Reports & figures**

  * Per-model detailed reports with diagnostics
  * Event duration histogram, FROC, sensitivity heatmaps
  * PSD comparison, frame-wise power, qualitative montages, error maps
* **Neuron annotation workbench**

  * large video review surface with zoom, fullscreen, contrast, and overlay controls
  * ROI-level accept/reject/unsure review
  * event-level accept/reject/unsure review
  * trace-level robust Kalman baseline/event visualization
  * local autosave to `annotations.json`
  * ROI and event TSV exports for downstream inverse-dynamics analysis
* **Clean, modular codebase** (easy to add new filters or detectors)

---

## Repository Structure

```
.
├── main.py
├── config.py
├── data_loader.py
├── utils.py
├── worker.py
├── core/
│   ├── filters.py
|   ├── detection.py
│   └── pipelines.py
├── evaluation/
│   ├── analysis.py
│   └── metrics.py
├── reporting/
│   ├── generators.py
│   └── plotters.py
├── tools/
│   ├── temporal_highpass_gaussian.ijm
│   ├── candidate_event_pipeline.groovy
│   ├── temporal_candidate_scoring.groovy
│   ├── generate_neuron_review_app.groovy
│   ├── build_neuron_workbench_v2.py
│   └── serve_neuron_workbench.py
├── docs/
│   ├── NEURON_WORKBENCH.md
│   └── PROCESSING_NOTES.md
├── Inputs/
└── Outputs/
```

---

## Installation

> Requires **Conda** (Anaconda or Miniconda). Python ≥ 3.8. A CUDA GPU is recommended.

1. Create the environment:

```bash
conda env create -f environment.yml
```

2. Activate it:

```bash
conda activate neuron-detection
```

3. (Optional) Update later:

```bash
conda env update -f environment.yml --prune
```

### Example `environment.yml`

> Save as `environment.yml` in the repo root.

```yaml
name: neuron-detection
channels:
  - pytorch
  - nvidia
  - conda-forge
dependencies:
  - python=3.10
  - numpy
  - pandas
  - scipy
  - matplotlib
  - scikit-image
  - tifffile
  - tqdm
  - psutil
  - pytorch
  - pytorch-cuda=12.1  # match your local CUDA driver; or remove if CPU-only
  - cudatoolkit=12.1   # optional; Conda-forge uses "cuda-toolkit"
  - pip
  - pip:
      - cupy-cuda12x    # optional, for GPU-accelerated Kalman–MCC (pick the right wheel)
```

**Notes**

* For **CPU-only**: remove the `pytorch-cuda`/`cudatoolkit` lines and `cupy-cuda12x`.
* For **different CUDA versions**, change `*-cuda12x` accordingly.

---

## Inputs

Place files in `Inputs/`:

* `video1_cropped_adj.tif` — your TIFF video (T×H×W)
* `Neuron and Blood Vessel labeled_CL(Video1_Neuron)_cropped_adj.csv` — neuron GT CSV
  Required columns: `ID, Start Frame, End Frame, X, Y`
* (Optional) Vessel GT CSV for FP taxonomy

Update paths in `config.py` if your filenames differ.

---

## Configuration

Edit **`config.py`** to control paths and parameter sweeps.

### CFAR & Shared Settings

```python
SHARED_PARAMS = {
    'distance_tolerance': [6],
    'neighborhood_config': [(3, 1)],
    'cfar_config': [{
        'type': 'local-separate-gamma',
        'gamma_radial_params': (9, 35),
        'kernel_size': (23, 23),
        'eps': 64
    }]
}
TRUNCATION_FPPI_LIMIT = 30.0
TOP_K_MODELS_TO_REPORT = 16
Z_SCORE_SWEEP = np.linspace(0, 2, 256)
```

### Choose Filters to Search

You can search **Gamma**, **Kalman–MCC**, or **both** (combined).
Uncomment / set either or both parameter blocks.

**Gamma example:**

```python
GAMMA_PARAMS = {
    'filter_type': ['gamma'],
    't_decay': [2**(-3) * i for i in range(9)],
    's_decay': [2**(-2) * i for i in range(3)],
}
```

**Kalman–MCC example:**

```python
KALMAN_PARAMS = {
    'filter_type': ['kalman_mcc'],
    'sigma': [2**(-2) * i for i in range(5)],
    'mu':    [2**(-2) * i for i in range(5)],
}
```

> The pipeline treats filters as interchangeable.
> If **both** `GAMMA_PARAMS` and `KALMAN_PARAMS` are defined, the grid search will run **each family separately** and also a **combined comparison** (to see the true overall best), while still reporting each family’s results individually.

---

## Running

### Python Grid Search

```bash
python main.py
```

What happens:

1. Load video & ground truth.
2. Build the parameter grid(s) for the selected filter(s).
3. Run **parallel grid search** (uses `NUM_WORKERS`).
4. Save `Outputs/GridSearch_Full_Report_*/…` with:

   * `all_grid_search_results.csv`
   * `top_models_at_100_tpr.csv`
   * `top_models_balanced.csv`
   * Per-model `Rank_*_Report/` folders
   * Figures (`.png`) and diagnostics (`.tif`, `.csv`)

### Neuron Review Workbench

The workbench path is intended for interactive scientific review of candidate
neurons and firing events. It depends on Fiji/ImageJ for TIFF stack handling and
uses stdlib Python for the local browser UI/autosave server. New samples should
be run through a dataset manifest so processed videos can be opened from one
index page.

For a concise lab-shareable explanation of the current resting-video algorithm,
waveforms, event markers, and untuned baseline status, see
[docs/RESTING_VIDEO_ALGORITHM_BRIEF.md](docs/RESTING_VIDEO_ALGORITHM_BRIEF.md).

1. Create a manifest for the TIFF:

```bash
python3 tools/create_dataset_manifest.py \
  --out Outputs/Manifests/calcium_rest_cropped.dataset.json \
  --dataset-id calcium_rest_cropped \
  --raw-video "Inputs/050126/050126/calcium_rest_cropped.tif" \
  --app-dir Outputs/NeuronReview/calcium_rest_cropped/app \
  --frame-rate-hz 5.0 \
  --pixel-size-microns 0.5
```

2. Run the current Fiji/Groovy pipeline and build the dashboard:

```bash
python3 tools/run_neuron_review_pipeline.py \
  --dataset-manifest Outputs/Manifests/calcium_rest_cropped.dataset.json \
  --fiji /home/jibby2k1/.local/bin/fiji
```

3. Start the multi-dataset autosave server:

```bash
python3 tools/serve_neuron_workbench.py --root-dir Outputs/NeuronReview --port 8765
```

4. Open:

```text
http://127.0.0.1:8765/
```

See [docs/NEURON_WORKBENCH.md](docs/NEURON_WORKBENCH.md) for annotation
shortcuts, autosave details, and export format notes.

---

## Outputs & Figures

* **FROC**: `fig_froc_top_k.png`
* **Sensitivity heatmaps**: `sensitivity_*_auc.png`
* **Event duration histogram**: `fig_event_duration_histogram.png`
* **PSD comparison**: `fig_psd_comparison.png`
* **Frame-wise power**: `fig_power_analysis_*.png`
* **Qualitative montage**: `fig_qualitative_montage.png`
* **Error maps**: `fig_fp_density.png`, `fig_fn_per_id.png`
* **Per-model video stack**: `diagnostic_video.tif` (raw | features | z-score | pre/post masks)

Workbench outputs are written under:

```bash
Outputs/NeuronReview/calcium_video_2/app/
```

Important workbench files:

* `review_data.json`: generated ROI, trace, event, and video metadata
* `annotations.json`: autosaved user labels and notes
* `roi_summary.tsv`: compact candidate ROI summary
* `frames/frame_###.png`: browser frame assets

`Outputs/` is ignored by git. Export ROI/event TSVs from the workbench when a
review pass is ready for downstream analysis.

---

## Tips & Performance

* **Kalman–MCC** is heavier than Gamma. To speed up:

  * Shrink the Kalman grid (`sigma`, `mu`)
  * Reduce CI bootstraps (see `analysis.calculate_bootstrap_ci`)
  * Limit frames for Kalman visualization: `KALMAN_MCC['max_frames_for_plots']`
  * Prefer GPU with CuPy if available
* Ensure your ground-truth CSV covers valid frame indices.
* If a plot looks off, delete the affected `Outputs/` folder and re-run to regenerate artifacts.
* For sparse firing events, prefer trace-level denoising over aggressive
  pixel-level video smoothing. See [docs/PROCESSING_NOTES.md](docs/PROCESSING_NOTES.md).
* Do not commit generated scientific data or output stacks. Commit reusable
  scripts and documentation only unless a data commit is explicitly intended.

---

## Troubleshooting

* **No models returned**
  Verify GT frames overlap with the video; loosen `distance_tolerance`.
* **CI very slow**
  Reduce bootstrap count and/or sample sizes; disable CI for exploratory runs.
* **Matplotlib missing**
  Recreate the Conda env or `conda install matplotlib`.

---

## License

MIT - do whatever you want, just don't blame us if it breaks.

---

## Citation

If this pipeline helps your work, please cite the repository in your methods or acknowledgements.
