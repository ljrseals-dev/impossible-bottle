# Impossible Bottle — Editable PSD Pipeline

A local pipeline for building an **Impossible Bottle** still-life as editable, layered artwork. The project combines prompt generation, optional ComfyUI-backed stages, custom ComfyUI nodes, and Photoshop PSD export workflows.

## Project layout

- `main.py` — single-file prompt/pipeline application; run with `python main.py`.
- `server.py` — FastAPI backend for the browser interface and job API.
- `index.html`, `app.js`, `styles.css` — browser interface.
- `custom_nodes/` — ComfyUI node packs for LaDe, OmniPSD, and PSD export.
- `workflows/` — example ComfyUI workflow JSON files.
- `install_nodes.sh`, `install_psd_tools.sh` — helper installation scripts.
- `verify.sh`, `verify_full.sh` — project verification scripts.
- `nested/artifacts/` — contents extracted from nested archives. Their directory levels are retained rather than flattened, so files from different archive layers are not silently overwritten.
- `outputs/` — created at runtime for generated files.

## Requirements

Python 3.10+ is recommended. Install the Python packages listed in `requirements.txt`:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\\Scripts\\activate`.

## Run the pipeline

### Single-file application

```bash
python main.py
```

The application prints/serves its interface at `http://localhost:8000`.

### Browser interface and API server

```bash
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

Then open `http://127.0.0.1:8000`.

## Optional ComfyUI integration

The backend supports an optional local ComfyUI instance. Start ComfyUI separately, then configure:

```bash
export USE_COMFY=1
export COMFY_URL=http://127.0.0.1:8188
```

The default is `USE_COMFY=0`, so the ComfyUI integration is not enabled unless requested. The server also accepts a `PORT` environment variable where applicable.

## Custom nodes and workflows

Review the scripts before running them. Install the node packs into your ComfyUI custom-nodes directory using the supplied helper:

```bash
COMFY_PATH=/path/to/ComfyUI ./install_nodes.sh
```

Workflow examples are in `workflows/`. Model checkpoints, LoRAs, external repositories, Photoshop, and ComfyUI are separate dependencies and are not bundled with this source tree.

## Verification

Run the included checks from the repository root:

```bash
bash verify.sh
bash verify_full.sh
```

These scripts exercise Python syntax, workflow JSON, PSD-writing paths, and custom-node registration. Some checks require optional Python packages and dependencies to be installed.

## Extraction note

The original archive contained multiple nested project trees. The primary project has been placed at the repository root; nested archive contents remain under `nested/artifacts/` to preserve their original separation. See [the extraction manifest](docs/EXTRACTION-MANIFEST.md) for the extraction record.
