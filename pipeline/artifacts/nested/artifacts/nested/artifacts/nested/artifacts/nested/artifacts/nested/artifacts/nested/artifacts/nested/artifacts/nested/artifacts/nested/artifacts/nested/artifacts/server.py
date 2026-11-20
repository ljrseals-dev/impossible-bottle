"""
Impossible Bottle → Editable PSD Pipeline API

  POST /api/prompt/{stage}   → prompt text
  POST /api/generate         → queue stage job (simulated or ComfyUI)
  GET  /api/job/{job_id}     → poll status
  GET  /api/health           → backend + optional Comfy ping

Run:
  pip install -r requirements.txt
  uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / "workflows"
OUT_DIR = ROOT / "outputs"
WORKFLOW_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)

COMFY_URL = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
USE_COMFY = os.environ.get("USE_COMFY", "0") == "1"

app = FastAPI(title="Impossible Bottle Pipeline", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS: dict[str, dict[str, Any]] = {}
CLIENT = httpx.AsyncClient(timeout=30.0)


class SceneConfig(BaseModel):
    bottleShape: str = "classic round, long neck"
    shipType: str = "19th-century brig"
    table: str = "dark oak table, grain left-to-right, worn finish"
    light: str = "motivated natural window light from camera left"
    aspect: str = "3:2"
    motion: str = "static"
    notes: str = ""


class GenerateRequest(BaseModel):
    stage: str
    workflow: Optional[str] = None
    # Accept either flat config fields or nested config
    bottleShape: Optional[str] = None
    shipType: Optional[str] = None
    table: Optional[str] = None
    light: Optional[str] = None
    aspect: Optional[str] = None
    motion: Optional[str] = None
    notes: Optional[str] = None
    config: Optional[SceneConfig] = None

    def resolved_config(self) -> SceneConfig:
        if self.config is not None:
            return self.config
        return SceneConfig(
            bottleShape=self.bottleShape or "classic round, long neck",
            shipType=self.shipType or "19th-century brig",
            table=self.table or "dark oak table, grain left-to-right, worn finish",
            light=self.light or "motivated natural window light from camera left",
            aspect=self.aspect or "3:2",
            motion=self.motion or "static",
            notes=self.notes or "",
        )


def _notes(c: SceneConfig) -> str:
    return f"\nExtra: {c.notes}" if c.notes.strip() else ""


def build_lade(c: SceneConfig) -> str:
    return f"""Create a multi-layer RGBA design of a physically plausible Impossible Bottle still life. Flexible layer count, each layer a semantically independent RGBA plate with clean alpha. No text, no watermarks, no logos.

Canvas: {c.aspect}, large-format still, shallow depth of field.

Layer "table": {c.table}, deep teal shadows in the grain, warm amber highlight rolloff where window light hits, fine film grain. No objects.

Layer "bottle_glass": Clear glass bottle standing upright, slightly left of center, {c.bottleShape}, wall thickness about 3–4 mm. Empty exterior silhouette only. Visible Fresnel edge reflections, slight thickness at the lip and base, clean alpha outside the glass. Do not paint the ship inside this layer.

Layer "ship_hull": Miniature {c.shipType} inside the bottle volume only. Wooden hull with aged oak grain, copper or brass fittings, bow facing camera-right. Scale must fit through the neck if the masts were folded. Clean alpha outside the hull.

Layer "masts_rigging": Hinged masts raised, tiny brass hinges visible at the mast bases, thread tension lines running up toward the bottle neck as if they were used to raise the masts after insertion. Canvas sails partially set, intricate rope rigging, brass blocks. Confined to the interior of the bottle. Clean alpha elsewhere.

Layer "sea_resin": Resin sea filling the bottom of the bottle interior, painted wave texture, subtle surface sheen matching the bottle's interior curvature, hull sitting in the resin. No exterior spill. Clean alpha outside the sea shape.

Lighting intent shared across layers: {c.light}, Rembrandt side light on the ship deck, dust visible only as a later grade, not painted into layers. Cool desaturated base, warm amber on wood and brass.{_notes(c)}"""


def build_snellcaster(c: SceneConfig) -> str:
    return f"""Snellcaster refraction pass — Impossible Bottle glass

Input: LaDe composite (or flattened still with glass mask)
Foreground mesh: bottle_glass layer alpha
Refractive index η: 1.52 (soda-lime glass)
Absorption: low, slight green tint optional (0.02–0.05)
Object pose: upright bottle, axis vertical, slight three-quarter toward camera
Auxiliary view: panorama centered at bottle centroid (for unobserved surfaces via refraction)
Ray-warp: apply Snell's Law self-warping each FLUX denoising step
Fresnel blend: edges of glass get reflection bias; interior transmits warped background + ship layers
Output: optically-correct refracted scene (masked PSNR target ~16.5, LPIPS ~0.24)

Bottle geometry notes: {c.bottleShape}; wall 3–4 mm; match curvature so ship/resin distort realistically.
Light for refraction consistency: {c.light}"""


def build_hbo(c: SceneConfig) -> str:
    return f"""[$cinematic-prompt-engine]
LOOK: HBO prestige drama. Succession restraint mixed with DTF St. Louis grain and Winning Time handmade texture. Not a commercial product shot.

Subject: An impossible bottle on a {c.table}. A {c.shipType} sealed inside clear glass ({c.bottleShape}), masts raised on tiny brass hinges, thread lines to the neck, resin sea under the hull.{_notes(c)}

Camera: Large-format still, 85mm equivalent, eye level, slight three-quarter. Aspect {c.aspect}. Shallow depth of field. Focus on the glass wall and the ship's midsection. Background falls off softly. No Dutch angle. No macro gimmick.

Lighting: {c.light}. Soft falloff. Rembrandt side light on the ship deck inside the glass. No fill from the opposite side except a faint bounce off the table. Dust in the shaft only where the window light crosses air, not a fog machine. No rim light from behind the bottle.

Color: Cool desaturated base. Saturation pulled back until wood and brass still have a soft electricity. Amber only in the window highlight and brass. Teal only in the oak shadows, never a teal-orange grade. Whites and blacks doubled, but digital sharpness tempered so edges do not crunch.

Texture: Fine film grain, mild halation on the window highlight, slight grease on the oak, honest glass. Handmade, not plastic, not CG, not octane-clean.

Refraction note: the ship and resin must distort through the curved glass according to real thickness. Edges of the bottle show Fresnel. Do not paint a flat ship sticker on the glass.

Anti-slop: no plastic materials, no unmotivated fill, no oversharpen, no HDR glow, no logo, no caption, no extra bottles, no people, no modern objects.

References: "Painterly, motivated, natural lighting, desaturated colors, and lots of depth" (Six Feet Under); soft electricity + tempered sharpness + grain/halation (DTF St. Louis); grainy, greasy, shiny, handmade (Winning Time)."""


def build_transparent(c: SceneConfig) -> str:
    return f"""A miniature {c.shipType} hull and hinged mast rigging assembly only, aged oak grain, brass hinges at mast bases, thread tension lines, canvas sails partially set, intricate rope and blocks, clean edges, isolated subject, transparent background, real alpha channel.{_notes(c)}

# Critical rules
- Describe only the subject. Never mention a table, bottle, room, or background.
- Do not write "on transparent background" after naming a surface — the model may render that surface.
- Prefer: GPT Image 2 with background="transparent", output_format="png"
  or Qwen-Image-2.1 with prompt suffix: "The image has alpha channel and the background is transparent." """


def build_sprite(c: SceneConfig) -> str:
    if c.motion == "static":
        return f"""# Motion: static still only — skip sprite-gen, or run a single-frame atlas for consistency checks.

sprite-gen gen --prompt "static miniature {c.shipType} rigging, hinged masts, no motion" --transparent
# Optional extract/compose if you need an atlas plate:
# sprite-gen extract --atlas sprite-sheet.png --output frames/
# sprite-gen compose-atlas --frames frames/ --output final_atlas.png"""
    if c.motion == "dust-motes":
        return """# Dust motes drifting in window light shaft (transparent loop)

sprite-gen video-loop --input base_still.png --output loop_frames/
# Or atlas path:
sprite-gen gen --prompt "fine dust particles drifting slowly through a diagonal light shaft, soft bokeh, transparent background" --transparent
sprite-gen extract --atlas sprite-sheet.png --output frames/
sprite-gen compose-atlas --frames frames/ --output dust_atlas.png

# Keep alpha clean: no chroma fringe; verify against white and black."""
    return f"""# Rigging sway loop (transparent)

sprite-gen video-loop --input base_ship_rigging.png --output loop_frames/

# Atlas path:
sprite-gen gen --prompt "miniature {c.shipType} hinged masts and canvas sails with subtle sway, brass hinges, thread lines, transparent background" --transparent
sprite-gen extract --atlas sprite-sheet.png --output frames/
sprite-gen compose-atlas --frames frames/ --output rigging_atlas.png

# Identity lock: one base still drives all rows; strip chroma to real alpha; verify no fringe on white/black."""


def build_omni(c: SceneConfig) -> str:
    return f"""OmniPSD image-to-PSD decomposition (optional refine pass)

Input: LaDe composite or Snellcaster-corrected render
Mode: iterative in-context edit — progressively extract foreground subjects and erase from canvas to reconstruct editable layers
Preserve: bottle glass alpha, ship hull, masts/rigging, sea/resin, table, background
Output: layered PSD with embedded smart objects
Notes: only run if LaDe layer count is insufficient; {c.aspect} canvas; do not merge glass with ship."""


def build_export(c: SceneConfig) -> str:
    return """Photoshop import steps

1. File → Open the LaDe / OmniPSD .psd — each layer arrives as an embedded smart object.
2. Confirm layer stack order (top → bottom): masts_rigging · ship_hull · sea_resin · bottle_glass · table · background.
3. Blend modes: bottle_glass → Normal, opacity ~92–96 to read glass; sea_resin → Normal.
4. Move glass, ship, and rigging independently. Rigging can be repositioned without touching bottle geometry.
5. If sprite-gen loop used: File → Import → Video Frames to Layers, then convert to Smart Object.
6. Export master: File → Export → Layers to Files (PNG-24 with alpha) for downstream use."""


BUILDERS = {
    "lade": build_lade,
    "snellcaster": build_snellcaster,
    "hbo": build_hbo,
    "transparent": build_transparent,
    "sprite": build_sprite,
    "omni": build_omni,
    "export": build_export,
}


def load_workflow(name: str) -> dict:
    path = WORKFLOW_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"workflow {name}.json not found in {WORKFLOW_DIR}")
    return json.loads(path.read_text())


def inject_prompt(workflow: dict, prompt: str, aspect: str) -> dict:
    blob = json.dumps(workflow)
    # Escape for JSON string embedding
    escaped = json.dumps(prompt)[1:-1]
    blob = blob.replace("{{PROMPT}}", escaped)
    blob = blob.replace("{{ASPECT}}", aspect)
    return json.loads(blob)


async def _run_simulated(job_id: str, stage: str, cfg: SceneConfig) -> None:
    job = JOBS[job_id]
    job["status"] = "running"
    for pct in (10, 35, 70, 95):
        await asyncio.sleep(0.35)
        job["progress"] = pct
    fn = BUILDERS[stage]
    job["result_prompt"] = fn(cfg)
    job["progress"] = 100
    job["status"] = "done"
    job["result"] = {"prompt": job["result_prompt"]}


async def _run_comfy(job_id: str, stage: str, workflow_name: str, cfg: SceneConfig) -> None:
    job = JOBS[job_id]
    job["status"] = "loading"
    prompt = BUILDERS[stage](cfg)
    workflow = inject_prompt(load_workflow(workflow_name), prompt, cfg.aspect)

    job["status"] = "queuing"
    r = await CLIENT.post(f"{COMFY_URL}/prompt", json={"prompt": workflow})
    r.raise_for_status()
    prompt_id = r.json()["prompt_id"]
    job["prompt_id"] = prompt_id
    job["status"] = "running"

    started = time.time()
    while True:
        h = await CLIENT.get(f"{COMFY_URL}/history/{prompt_id}")
        h.raise_for_status()
        hist = h.json().get(prompt_id)
        if hist:
            result = _extract_result(hist.get("outputs", {}))
            job["status"] = "done"
            job["progress"] = 100
            job["result_prompt"] = prompt
            job["result"] = result or {"prompt": prompt}
            if result and result.get("psd_url"):
                job["psd_path"] = result["psd_url"]
            return
        job["progress"] = min(90, job.get("progress", 5) + 5)
        if time.time() - started > 1200:
            job["status"] = "error"
            job["error"] = "timeout"
            return
        await asyncio.sleep(1.5)


def _extract_result(outputs: dict) -> Optional[dict]:
    for _node_id, out in outputs.items():
        for key in ("images", "gifs", "files"):
            for item in out.get(key, []):
                fn = item.get("filename")
                if not fn:
                    continue
                sub = item.get("subfolder", "")
                # Proxy via our /outputs if files are copied, else Comfy view URL
                view = f"{COMFY_URL}/view?filename={fn}"
                if sub:
                    view += f"&subfolder={sub}"
                if fn.lower().endswith((".psd", ".tif", ".tiff")):
                    return {"psd_url": view, "filename": fn}
                return {"image_url": view, "filename": fn}
    return None


async def _run_job(job_id: str, stage: str, workflow_name: Optional[str], cfg: SceneConfig) -> None:
    try:
        if USE_COMFY and workflow_name:
            await _run_comfy(job_id, stage, workflow_name, cfg)
        else:
            await _run_simulated(job_id, stage, cfg)
    except Exception as exc:  # noqa: BLE001
        job = JOBS.get(job_id)
        if job:
            job["status"] = "error"
            job["error"] = str(exc)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    comfy = False
    try:
        r = await CLIENT.get(f"{COMFY_URL}/system_stats", timeout=2.0)
        comfy = r.status_code == 200
    except Exception:
        comfy = False
    return {
        "ok": True,
        "service": "impossible-bottle-pipeline",
        "version": app.version,
        "comfy": comfy,
        "use_comfy": USE_COMFY,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/prompt/{stage}")
async def api_prompt(stage: str, body: SceneConfig) -> dict[str, str]:
    fn = BUILDERS.get(stage)
    if fn is None:
        raise HTTPException(404, f"unknown stage: {stage}")
    return {"stage": stage, "prompt": fn(body)}


@app.post("/api/generate")
async def api_generate(req: GenerateRequest) -> dict[str, str]:
    if req.stage not in BUILDERS:
        raise HTTPException(400, f"unknown stage: {req.stage}")
    cfg = req.resolved_config()
    workflow = req.workflow or req.stage
    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = {
        "job_id": job_id,
        "stage": req.stage,
        "status": "queued",
        "progress": 0,
        "result_prompt": None,
        "psd_path": None,
        "result": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": cfg.model_dump(),
    }
    asyncio.create_task(_run_job(job_id, req.stage, workflow if req.stage != "export" else None, cfg))
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
async def api_job(job_id: str) -> dict[str, Any]:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    return job


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(ROOT / "index.html")


@app.get("/app.js")
async def app_js() -> FileResponse:
    return FileResponse(ROOT / "app.js", media_type="application/javascript")


@app.get("/styles.css")
async def styles_css() -> FileResponse:
    return FileResponse(ROOT / "styles.css", media_type="text/css")


app.mount("/outputs", StaticFiles(directory=str(OUT_DIR)), name="outputs")
