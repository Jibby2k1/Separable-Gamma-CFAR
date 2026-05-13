#!/usr/bin/env python3
"""Serve the neuron annotation workbench with local autosave.

Usage:
    python3 tools/serve_neuron_workbench.py
    python3 tools/serve_neuron_workbench.py --root-dir Outputs/NeuronReview

Then open:
    http://127.0.0.1:8765/
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from neurobench.workbench.server import (
    ALLOWED_BACKENDS,
    DEFAULT_APP_DIR,
    GenerationJob,
    JOBS,
    JobRegistry,
    WorkbenchHandler,
    configure_workbench_handler,
    create_workbench_server,
    environment_report,
    execute_generation_job,
    generated_dataset_manifest,
    load_json,
    main,
    owner_token_matches,
    owner_token_required,
    run_generation_params,
    serve_workbench,
)


if __name__ == "__main__":
    main()
