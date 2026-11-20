#!/usr/bin/env python3
"""
Impossible Bottle → Editable PSD Pipeline (single-file)
Run:  python main.py
Open: http://localhost:8000

Optional env:
  USE_COMFY=1
  COMFY_URL=http://127.0.0.1:8188
  PORT=8000
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

PORT = int(os.environ.get("PORT", "8000"))
USE_COMFY = os.environ.get("USE_COMFY", "0") == "1"
COMFY_URL = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / "workflows"
OUT_DIR = ROOT / "outputs"
WORKFLOW_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)

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

JOBS: dict[str, dict[str, Any]] = {}

def _notes(c: SceneConfig) -> str:
    return f"\nExtra: {c.notes}" if c.notes.strip() else ""

def build_lade(c: SceneConfig) -> str:
    return f"""Create a multi-layer RGBA design of a physically plausible Impossible Bottle still life. Flexible layer count, each layer a semantically independent RGBA plate with clean alpha. No text, no watermarks, no logos.

Canvas: {c.aspect}, large-format still, shallow depth of field.

Layer "table": {c.table}, deep teal shadows in the grain, warm amber highlight rolloff where window light hits, fine film grain. No objects.

Layer "bottle_glass": Clear glass bottle standing upright, slightly left of center, {c.bottleShape}, wall thickness about 3–4 mm. Empty exterior silhouette only. Visible Fresnel edge reflections, slight thickness at the lip and base, clean alpha outside the glass. Do not paint the ship inside this layer.

Layer "ship_hull": Miniature {c.shipType} inside the bottle volume only. Wooden hull with aged oak grain, copper or brass fittings, bow facing camera-right. Scale must fit through the neck if the masts were folded. Clean alpha outside the hull.

Layer "masts_rigging": Hinged masts raised, tiny brass hinges visible at the mast bases, thread tension lines running up toward the bottle neck as if they were used to raise the masts after insertion. Canvas sails partially set, intricate rope rigging, brass blocks. Confined to the interior of the bottle. Clean alpha elsewhere.

Layer "sea_resin": Resin sea filling the bottom of the bottle interior, painted wave texture, subtle surface sheen matching the bottle\'s interior curvature, hull sitting in the resin. No exterior spill. Clean alpha outside the sea shape.

Lighting intent shared across layers: {c.light}, Rembrandt side light on the ship deck, dust visible only as a later grade, not painted into layers. Cool desaturated base, warm amber on wood and brass.{_notes(c)}"""

def build_snellcaster(c: SceneConfig) -> str:
    return f"""Snellcaster refraction pass — Impossible Bottle glass

Input: LaDe composite (or flattened still with glass mask)
Foreground mesh: bottle_glass layer alpha
Refractive index η: 1.52 (soda-lime glass)
Absorption: low, slight green tint optional (0.02–0.05)
Object pose: upright bottle, axis vertical, slight three-quarter toward camera
Auxiliary view: panorama centered at bottle centroid (for unobserved surfaces via refraction)
Ray-warp: apply Snell\'s Law self-warping each FLUX denoising step
Fresnel blend: edges of glass get reflection bias; interior transmits warped background + ship layers
Output: optically-correct refracted scene (masked PSNR target ~16.5, LPIPS ~0.24)

Bottle geometry notes: {c.bottleShape}; wall 3–4 mm; match curvature so ship/resin distort realistically.
Light for refraction consistency: {c.light}"""

def build_hbo(c: SceneConfig) -> str:
    return f"""[$cinematic-prompt-engine]
LOOK: HBO prestige drama. Succession restraint mixed with DTF St. Louis grain and Winning Time handmade texture. Not a commercial product shot.

Subject: An impossible bottle on a {c.table}. A {c.shipType} sealed inside clear glass ({c.bottleShape}), masts raised on tiny brass hinges, thread lines to the neck, resin sea under the hull.{_notes(c)}

Camera: Large-format still, 85mm equivalent, eye level, slight three-quarter. Aspect {c.aspect}. Shallow depth of field. Focus on the glass wall and the ship\'s midsection. Background falls off softly. No Dutch angle. No macro gimmick.

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
sprite-gen gen --prompt "fine dust particles drifting slowly through a diagonal light shaft, soft bokeh, transparent background" --transparent
sprite-gen extract --atlas sprite-sheet.png --output frames/
sprite-gen compose-atlas --frames frames/ --output dust_atlas.png

# Keep alpha clean: no chroma fringe; verify against white and black."""
    return f"""# Rigging sway loop (transparent)

sprite-gen video-loop --input base_ship_rigging.png --output loop_frames/
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

STARTER_WORKFLOW = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-dev.safetensors"}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{PROMPT}}", "clip": ["1", 1]}},
    "3": {"class_type": "EmptyLatentImage", "inputs": {"width": 1216, "height": 832, "batch_size": 1}},
    "4": {"class_type": "KSampler", "inputs": {
        "model": ["1", 0], "positive": ["2", 0], "negative": ["2", 0],
        "latent_image": ["3", 0], "seed": 42, "steps": 28, "cfg": 3.5,
        "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
    "5": {"class_type": "VAEDecode", "inputs": {"samples": ["4", 0], "vae": ["1", 2]}},
    "6": {"class_type": "SaveImage", "inputs": {"images": ["5", 0], "filename_prefix": "lade/impossible_bottle"}},
}

for name in ("lade", "snellcaster", "hbo", "transparent", "sprite", "omni"):
    p = WORKFLOW_DIR / f"{name}.json"
    if not p.exists():
        p.write_text(json.dumps(STARTER_WORKFLOW, indent=2))

app = FastAPI(title="Impossible Bottle Pipeline", version="1.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

async def _run_job(job_id: str, stage: str, cfg: SceneConfig) -> None:
    job = JOBS[job_id]
    try:
        job["status"] = "running"
        for pct in (10, 35, 70, 95):
            await asyncio.sleep(0.35)
            job["progress"] = pct
        prompt = BUILDERS[stage](cfg)
        job["result_prompt"] = prompt
        job["result"] = {"prompt": prompt}
        job["progress"] = 100
        job["status"] = "done"
    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)

@app.get("/api/health")
async def health() -> dict[str, Any]:
    comfy = False
    if USE_COMFY:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{COMFY_URL}/system_stats")
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
    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = {
        "job_id": job_id,
        "stage": req.stage,
        "status": "queued",
        "progress": 0,
        "result_prompt": None,
        "result": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": cfg.model_dump(),
    }
    asyncio.create_task(_run_job(job_id, req.stage, cfg))
    return {"job_id": job_id}

@app.get("/api/job/{job_id}")
async def api_job(job_id: str) -> dict[str, Any]:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    return job

# Embedded UI (inlined from index.html + styles.css + app.js)
HTML_PAGE = json.loads("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n  <meta charset=\"UTF-8\" />\n  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n  <title>Impossible Bottle \u2192 Editable PSD Pipeline</title>\n  <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\" />\n  <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin />\n  <link href=\"https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600;700&display=swap\" rel=\"stylesheet\" />\n  <style>\n:root {\n  --bg: #0c0e12;\n  --bg-elevated: #13171f;\n  --bg-panel: #161b24;\n  --border: #242b38;\n  --border-strong: #323b4d;\n  --text: #e8eaef;\n  --text-muted: #8b93a7;\n  --text-dim: #5c6578;\n  --accent: #c4a574;\n  --accent-soft: rgba(196, 165, 116, 0.14);\n  --accent-border: rgba(196, 165, 116, 0.35);\n  --teal: #4a7c8c;\n  --teal-soft: rgba(74, 124, 140, 0.15);\n  --success: #6aab8e;\n  --danger: #c77b7b;\n  --radius: 12px;\n  --radius-sm: 8px;\n  --font: \"Inter\", system-ui, sans-serif;\n  --serif: \"Instrument Serif\", Georgia, serif;\n  --mono: \"IBM Plex Mono\", ui-monospace, monospace;\n  --shadow: 0 12px 40px rgba(0, 0, 0, 0.35);\n}\n\n* {\n  box-sizing: border-box;\n}\n\nhtml, body {\n  margin: 0;\n  min-height: 100%;\n  background: var(--bg);\n  color: var(--text);\n  font-family: var(--font);\n  font-size: 15px;\n  line-height: 1.5;\n  -webkit-font-smoothing: antialiased;\n}\n\nbody {\n  background-image:\n    radial-gradient(ellipse 80% 50% at 10% -10%, rgba(74, 124, 140, 0.12), transparent),\n    radial-gradient(ellipse 60% 40% at 90% 0%, rgba(196, 165, 116, 0.08), transparent);\n}\n\n.app {\n  max-width: 1200px;\n  margin: 0 auto;\n  padding: 28px 24px 48px;\n}\n\n.header {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  gap: 16px;\n  margin-bottom: 28px;\n  flex-wrap: wrap;\n}\n\n.brand {\n  display: flex;\n  align-items: center;\n  gap: 14px;\n}\n\n.brand-mark {\n  width: 40px;\n  height: 40px;\n  border-radius: 50%;\n  background:\n    radial-gradient(circle at 35% 30%, rgba(255, 255, 255, 0.35), transparent 40%),\n    linear-gradient(145deg, #7a9eab 0%, #2a4550 45%, #1a2a32 100%);\n  border: 1px solid rgba(255, 255, 255, 0.12);\n  box-shadow: inset 0 0 12px rgba(255, 255, 255, 0.15), 0 4px 16px rgba(0, 0, 0, 0.4);\n  position: relative;\n}\n\n.brand-mark::after {\n  content: \"\";\n  position: absolute;\n  inset: 28% 32% 22% 32%;\n  background: linear-gradient(180deg, #8b6b4a, #5c4030);\n  border-radius: 2px;\n  opacity: 0.85;\n}\n\n.brand h1 {\n  margin: 0;\n  font-family: var(--serif);\n  font-size: 1.75rem;\n  font-weight: 400;\n  letter-spacing: -0.02em;\n}\n\n.tagline {\n  margin: 2px 0 0;\n  color: var(--text-muted);\n  font-size: 0.8rem;\n  letter-spacing: 0.04em;\n  text-transform: uppercase;\n}\n\n.header-actions {\n  display: flex;\n  gap: 10px;\n}\n\n.btn {\n  border: 1px solid var(--border-strong);\n  background: var(--bg-elevated);\n  color: var(--text);\n  font-family: var(--font);\n  font-size: 0.875rem;\n  font-weight: 500;\n  padding: 9px 14px;\n  border-radius: var(--radius-sm);\n  cursor: pointer;\n  transition: background 0.15s, border-color 0.15s, color 0.15s;\n}\n\n.btn:hover {\n  border-color: var(--text-dim);\n  background: #1a2030;\n}\n\n.btn.primary {\n  background: var(--accent);\n  border-color: var(--accent);\n  color: #1a140c;\n}\n\n.btn.primary:hover {\n  background: #d4b584;\n  border-color: #d4b584;\n}\n\n.btn.secondary {\n  background: var(--accent-soft);\n  border-color: var(--accent-border);\n  color: var(--accent);\n}\n\n.btn.secondary:hover {\n  background: rgba(196, 165, 116, 0.22);\n}\n\n.btn.ghost {\n  background: transparent;\n}\n\n.btn:disabled {\n  opacity: 0.45;\n  cursor: not-allowed;\n}\n\n.stages-nav {\n  display: flex;\n  gap: 6px;\n  overflow-x: auto;\n  padding-bottom: 4px;\n  margin-bottom: 20px;\n  scrollbar-width: thin;\n}\n\n.stage-tab {\n  flex: 0 0 auto;\n  border: 1px solid var(--border);\n  background: var(--bg-elevated);\n  color: var(--text-muted);\n  font-size: 0.78rem;\n  font-weight: 500;\n  padding: 8px 12px;\n  border-radius: 999px;\n  cursor: pointer;\n  white-space: nowrap;\n  transition: all 0.15s;\n}\n\n.stage-tab:hover {\n  color: var(--text);\n  border-color: var(--border-strong);\n}\n\n.stage-tab.active {\n  background: var(--accent-soft);\n  border-color: var(--accent-border);\n  color: var(--accent);\n}\n\n.stage-tab.done {\n  color: var(--success);\n}\n\n.stage-tab.done.active {\n  border-color: rgba(106, 171, 142, 0.45);\n  background: rgba(106, 171, 142, 0.12);\n}\n\n.main {\n  display: grid;\n  grid-template-columns: 1fr 300px;\n  gap: 16px;\n  align-items: start;\n}\n\n@media (max-width: 900px) {\n  .main {\n    grid-template-columns: 1fr;\n  }\n}\n\n.panel {\n  background: var(--bg-panel);\n  border: 1px solid var(--border);\n  border-radius: var(--radius);\n  padding: 20px 22px;\n  box-shadow: var(--shadow);\n}\n\n.config-panel {\n  grid-column: 1 / -1;\n}\n\n.panel-head {\n  margin-bottom: 16px;\n}\n\n.panel-head.row {\n  display: flex;\n  justify-content: space-between;\n  align-items: flex-start;\n  gap: 16px;\n  flex-wrap: wrap;\n}\n\n.panel-head h2 {\n  margin: 0 0 4px;\n  font-size: 1.15rem;\n  font-weight: 600;\n}\n\n.panel-head p {\n  margin: 0;\n  color: var(--text-muted);\n  font-size: 0.9rem;\n}\n\n.stage-kicker {\n  font-size: 0.72rem !important;\n  letter-spacing: 0.08em;\n  text-transform: uppercase;\n  color: var(--accent) !important;\n  margin-bottom: 4px !important;\n}\n\n.stage-tools {\n  display: flex;\n  gap: 8px;\n  flex-shrink: 0;\n}\n\n.config-grid {\n  display: grid;\n  grid-template-columns: repeat(3, 1fr);\n  gap: 14px 16px;\n}\n\n@media (max-width: 700px) {\n  .config-grid {\n    grid-template-columns: 1fr 1fr;\n  }\n}\n\n@media (max-width: 480px) {\n  .config-grid {\n    grid-template-columns: 1fr;\n  }\n}\n\n.config-grid label {\n  display: flex;\n  flex-direction: column;\n  gap: 6px;\n  font-size: 0.78rem;\n  font-weight: 500;\n  color: var(--text-muted);\n  letter-spacing: 0.02em;\n}\n\n.config-grid label.full {\n  grid-column: 1 / -1;\n}\n\n.config-grid select,\n.config-grid textarea {\n  font-family: var(--font);\n  font-size: 0.9rem;\n  color: var(--text);\n  background: var(--bg);\n  border: 1px solid var(--border);\n  border-radius: var(--radius-sm);\n  padding: 10px 12px;\n  outline: none;\n  transition: border-color 0.15s;\n}\n\n.config-grid select:focus,\n.config-grid textarea:focus {\n  border-color: var(--accent-border);\n}\n\n.config-grid textarea {\n  resize: vertical;\n  min-height: 64px;\n}\n\n.prompt-block {\n  margin-top: 4px;\n}\n\n.prompt-meta {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  margin-bottom: 8px;\n  font-size: 0.75rem;\n  color: var(--text-dim);\n  text-transform: uppercase;\n  letter-spacing: 0.06em;\n}\n\n.prompt-meta .hint {\n  color: var(--success);\n  text-transform: none;\n  letter-spacing: 0;\n}\n\n.prompt-output {\n  margin: 0;\n  padding: 16px 18px;\n  background: var(--bg);\n  border: 1px solid var(--border);\n  border-radius: var(--radius-sm);\n  font-family: var(--mono);\n  font-size: 0.78rem;\n  line-height: 1.55;\n  color: #c5cbd8;\n  white-space: pre-wrap;\n  word-break: break-word;\n  max-height: 420px;\n  overflow: auto;\n}\n\n.stage-extra {\n  margin-top: 16px;\n}\n\n.extra-card {\n  background: var(--bg);\n  border: 1px solid var(--border);\n  border-radius: var(--radius-sm);\n  padding: 14px 16px;\n}\n\n.extra-card h3 {\n  margin: 0 0 8px;\n  font-size: 0.85rem;\n  font-weight: 600;\n  color: var(--accent);\n}\n\n.extra-card ul,\n.extra-card ol {\n  margin: 0;\n  padding-left: 18px;\n  color: var(--text-muted);\n  font-size: 0.88rem;\n}\n\n.extra-card li {\n  margin-bottom: 4px;\n}\n\n.extra-card code {\n  font-family: var(--mono);\n  font-size: 0.8em;\n  color: #b8c0d0;\n  background: rgba(255, 255, 255, 0.04);\n  padding: 1px 5px;\n  border-radius: 4px;\n}\n\n.param-grid {\n  display: grid;\n  grid-template-columns: 1fr 1fr;\n  gap: 8px 16px;\n  font-size: 0.85rem;\n}\n\n.param-grid dt {\n  color: var(--text-dim);\n  font-size: 0.75rem;\n  text-transform: uppercase;\n  letter-spacing: 0.04em;\n}\n\n.param-grid dd {\n  margin: 0 0 8px;\n  color: var(--text);\n  font-family: var(--mono);\n  font-size: 0.8rem;\n}\n\n.checklist {\n  list-style: none;\n  margin: 0;\n  padding: 0;\n}\n\n.checklist li {\n  display: flex;\n  align-items: flex-start;\n  gap: 10px;\n  padding: 10px 0;\n  border-bottom: 1px solid var(--border);\n  font-size: 0.85rem;\n  color: var(--text-muted);\n  cursor: pointer;\n  user-select: none;\n}\n\n.checklist li:last-child {\n  border-bottom: none;\n}\n\n.checklist li:hover {\n  color: var(--text);\n}\n\n.checklist input {\n  margin-top: 3px;\n  accent-color: var(--accent);\n  flex-shrink: 0;\n}\n\n.checklist li.checked {\n  color: var(--success);\n}\n\n.progress {\n  margin-top: 16px;\n}\n\n.progress-bar {\n  height: 4px;\n  background: var(--border);\n  border-radius: 2px;\n  overflow: hidden;\n}\n\n.progress-bar span {\n  display: block;\n  height: 100%;\n  width: 0%;\n  background: linear-gradient(90deg, var(--teal), var(--accent));\n  transition: width 0.25s ease;\n}\n\n#progress-label {\n  margin: 8px 0 0;\n  font-size: 0.78rem;\n  color: var(--text-dim);\n}\n\n.footer {\n  margin-top: 28px;\n  text-align: center;\n  color: var(--text-dim);\n  font-size: 0.75rem;\n  letter-spacing: 0.02em;\n}\n\n.footer p {\n  margin: 0;\n}\n\n</style>\n</head>\n<body>\n  <div class=\"app\">\n    <header class=\"header\">\n      <div class=\"brand\">\n        <span class=\"brand-mark\" aria-hidden=\"true\"></span>\n        <div>\n          <h1>Impossible Bottle</h1>\n          <p class=\"tagline\">Editable PSD Pipeline \u00b7 HBO Edition</p>\n        </div>\n      </div>\n      <div class=\"header-actions\">\n        <button type=\"button\" class=\"btn ghost\" id=\"btn-reset\">Reset</button>\n        <button type=\"button\" class=\"btn primary\" id=\"btn-export-pack\">Export prompt pack</button>\n      </div>\n    </header>\n\n    <nav class=\"stages-nav\" id=\"stages-nav\" aria-label=\"Pipeline stages\"></nav>\n\n    <main class=\"main\">\n      <section class=\"panel config-panel\" id=\"panel-config\">\n        <div class=\"panel-head\">\n          <h2>Scene configuration</h2>\n          <p>Drive every stage from one composition. Changes regenerate LaDe tokens and the HBO LOOK card.</p>\n        </div>\n\n        <form id=\"config-form\" class=\"config-grid\">\n          <label>\n            <span>Bottle shape</span>\n            <select name=\"bottleShape\" id=\"bottleShape\">\n              <option value=\"classic round, long neck\">Classic round \u00b7 long neck</option>\n              <option value=\"square body, short neck\">Square body</option>\n              <option value=\"cylindrical pharmacy bottle\">Pharmacy cylinder</option>\n              <option value=\"demijohn with wide belly\">Demijohn</option>\n            </select>\n          </label>\n\n          <label>\n            <span>Ship type</span>\n            <select name=\"shipType\" id=\"shipType\">\n              <option value=\"19th-century brig\">19th-century brig</option>\n              <option value=\"19th-century schooner\">Schooner</option>\n              <option value=\"full-rigged ship\">Full-rigged ship</option>\n              <option value=\"clipper ship\">Clipper</option>\n            </select>\n          </label>\n\n          <label>\n            <span>Table surface</span>\n            <select name=\"table\" id=\"table\">\n              <option value=\"dark oak table, grain left-to-right, worn finish\">Dark oak</option>\n              <option value=\"black walnut table, tight grain, matte oil finish\">Black walnut</option>\n              <option value=\"weathered pine workbench, tool scars\">Weathered pine</option>\n              <option value=\"polished mahogany sideboard\">Mahogany</option>\n            </select>\n          </label>\n\n          <label>\n            <span>Window light</span>\n            <select name=\"light\" id=\"light\">\n              <option value=\"motivated natural window light from camera left\">Camera left</option>\n              <option value=\"soft overcast light from camera right\">Camera right</option>\n              <option value=\"low late-afternoon raking light from behind left\">Raking rear-left</option>\n              <option value=\"north window diffuse light, minimal hard shadows\">North diffuse</option>\n            </select>\n          </label>\n\n          <label>\n            <span>Aspect ratio</span>\n            <select name=\"aspect\" id=\"aspect\">\n              <option value=\"3:2\">3:2 large format</option>\n              <option value=\"16:9\">16:9 cinematic</option>\n              <option value=\"4:5\">4:5 portrait still</option>\n              <option value=\"1:1\">1:1 square</option>\n            </select>\n          </label>\n\n          <label>\n            <span>Motion</span>\n            <select name=\"motion\" id=\"motion\">\n              <option value=\"static\">Static still only</option>\n              <option value=\"rigging-sway\">Transparent rigging sway loop</option>\n              <option value=\"dust-motes\">Dust motes in light shaft</option>\n            </select>\n          </label>\n\n          <label class=\"full\">\n            <span>Extra notes (optional)</span>\n            <textarea name=\"notes\" id=\"notes\" rows=\"2\" placeholder=\"e.g. copper fittings oxidized, sails half-furled, cork in neck\u2026\"></textarea>\n          </label>\n        </form>\n      </section>\n\n      <section class=\"panel stage-panel\" id=\"panel-stage\">\n        <div class=\"panel-head row\">\n          <div>\n            <p class=\"stage-kicker\" id=\"stage-kicker\">Stage 1</p>\n            <h2 id=\"stage-title\">Layered generation \u00b7 LaDe</h2>\n            <p id=\"stage-desc\">Flexible semantic RGBA layers from a single structured prompt.</p>\n          </div>\n          <div class=\"stage-tools\">\n            <button type=\"button\" class=\"btn ghost\" id=\"btn-copy-prompt\">Copy prompt</button>\n            <button type=\"button\" class=\"btn secondary\" id=\"btn-mark-done\">Mark complete</button>\n          </div>\n        </div>\n\n        <div class=\"prompt-block\">\n          <div class=\"prompt-meta\">\n            <span id=\"prompt-label\">LaDe tokens</span>\n            <span class=\"hint\" id=\"copy-status\"></span>\n          </div>\n          <pre id=\"prompt-output\" class=\"prompt-output\" tabindex=\"0\"></pre>\n        </div>\n\n        <div class=\"stage-extra\" id=\"stage-extra\"></div>\n      </section>\n\n      <aside class=\"panel checklist-panel\">\n        <div class=\"panel-head\">\n          <h2>Build checklist</h2>\n          <p>Local stack readiness for the full pipeline.</p>\n        </div>\n        <ul class=\"checklist\" id=\"checklist\"></ul>\n        <div class=\"progress\">\n          <div class=\"progress-bar\"><span id=\"progress-fill\"></span></div>\n          <p id=\"progress-label\">0 / 8 ready</p>\n        </div>\n      </aside>\n    </main>\n\n    <footer class=\"footer\">\n      <p>Local-first \u00b7 LaDe \u2192 Snellcaster \u2192 HBO LOOK \u2192 transparent elements \u2192 sprite-gen \u2192 OmniPSD \u2192 Photoshop smart objects</p>\n    </footer>\n  </div>\n\n  <script>\n(function () {\n  \"use strict\";\n\n  const API = \"\"; // same-origin; set to \"http://127.0.0.1:8000\" if served elsewhere\n  const COMFY_POLL_MS = 1500;\n  const COMFY_TIMEOUT_MS = 20 * 60 * 1000;\n\n  const STAGES = [\n    { id: \"lade\",        num: 1, title: \"Layered generation \u00b7 LaDe\",        short: \"1 \u00b7 LaDe\",        desc: \"Flexible semantic RGBA layers from a single structured prompt.\", promptLabel: \"LaDe tokens\",           workflow: \"lade\" },\n    { id: \"snellcaster\", num: 2, title: \"Refraction physics \u00b7 Snellcaster\", short: \"2 \u00b7 Snellcaster\", desc: \"Training-free Snell's Law ray-warping on the glass layer.\",       promptLabel: \"Snellcaster parameters\", workflow: \"snellcaster\" },\n    { id: \"hbo\",         num: 3, title: \"Cinematic grade \u00b7 HBO LOOK\",       short: \"3 \u00b7 HBO LOOK\",    desc: \"DP-inspired LOOK card.\",                                          promptLabel: \"HBO LOOK card\",         workflow: \"hbo\" },\n    { id: \"transparent\", num: 4, title: \"Transparent elements\",             short: \"4 \u00b7 Alpha\",       desc: \"Native RGBA generation for isolatable plates.\",                   promptLabel: \"Transparent subject prompt\", workflow: \"transparent\" },\n    { id: \"sprite\",      num: 5, title: \"Motion frames \u00b7 sprite-gen\",       short: \"5 \u00b7 Motion\",      desc: \"Still \u2192 transparent motion loops or atlas.\",                      promptLabel: \"sprite-gen commands\",   workflow: \"sprite\" },\n    { id: \"omni\",        num: 6, title: \"Layer refinement \u00b7 OmniPSD\",       short: \"6 \u00b7 OmniPSD\",     desc: \"Optional image-to-PSD decomposition.\",                            promptLabel: \"OmniPSD notes\",         workflow: \"omni\" },\n    { id: \"export\",      num: 7, title: \"Export \u00b7 Photoshop\",               short: \"7 \u00b7 PSD\",         desc: \"Smart-object layered PSD.\",                                       promptLabel: \"Photoshop import steps\", workflow: null },\n  ];\n\n  const CHECKLIST = [\n    { id: \"lade\",      label: \"LaDe cloned + deps installed\" },\n    { id: \"snell\",     label: \"Snellcaster cloned + FLUX weights\" },\n    { id: \"cinematic\", label: \"AI_Cinematic_Prompt / LOOK card ready\" },\n    { id: \"alpha\",     label: \"GPT Image 2 key or Qwen-Image-2.1 weights\" },\n    { id: \"sprite\",    label: \"sprite-gen CLI installed + tested\" },\n    { id: \"omni\",      label: \"OmniPSD cloned (optional refine)\" },\n    { id: \"comfy\",     label: \"ComfyUI running on :8188\" },\n    { id: \"ps\",        label: \"Photoshop ready for smart objects\" },\n  ];\n\n  const STORAGE_KEY = \"ib.pipeline.v1\";\n\n  const state = {\n    stageIndex: 0,\n    stageDone: {},\n    checklist: loadChecklist(),\n    job: null,\n    pollTimer: null,\n    backendUp: false,\n  };\n\n  const els = {\n    nav:          document.getElementById(\"stages-nav\"),\n    form:         document.getElementById(\"config-form\"),\n    stageKicker:  document.getElementById(\"stage-kicker\"),\n    stageTitle:   document.getElementById(\"stage-title\"),\n    stageDesc:    document.getElementById(\"stage-desc\"),\n    promptLabel:  document.getElementById(\"prompt-label\"),\n    promptOutput: document.getElementById(\"prompt-output\"),\n    stageExtra:   document.getElementById(\"stage-extra\"),\n    copyStatus:   document.getElementById(\"copy-status\"),\n    checklist:    document.getElementById(\"checklist\"),\n    progressFill: document.getElementById(\"progress-fill\"),\n    progressLabel:document.getElementById(\"progress-label\"),\n    btnCopy:      document.getElementById(\"btn-copy-prompt\"),\n    btnDone:      document.getElementById(\"btn-mark-done\"),\n    btnReset:     document.getElementById(\"btn-reset\"),\n    btnExport:    document.getElementById(\"btn-export-pack\"),\n  };\n\n  function config() {\n    const fd = new FormData(els.form);\n    return {\n      bottleShape: fd.get(\"bottleShape\") || \"classic round, long neck\",\n      shipType:    fd.get(\"shipType\")    || \"19th-century brig\",\n      table:       fd.get(\"table\")       || \"dark oak table, grain left-to-right, worn finish\",\n      light:       fd.get(\"light\")       || \"motivated natural window light from camera left\",\n      aspect:      fd.get(\"aspect\")      || \"3:2\",\n      motion:      fd.get(\"motion\")      || \"static\",\n      notes:       (fd.get(\"notes\") || \"\").trim(),\n    };\n  }\n  const notesLine = (c) => (c.notes ? `\\nExtra: ${c.notes}` : \"\");\n\n  function buildLade(c) {\n    return `Create a multi-layer RGBA design of a physically plausible Impossible Bottle still life. Flexible layer count, each layer a semantically independent RGBA plate with clean alpha. No text, no watermarks, no logos.\n\nCanvas: ${c.aspect}, large-format still, shallow depth of field.\n\nLayer \"table\": ${c.table}, deep teal shadows in the grain, warm amber highlight rolloff where window light hits, fine film grain. No objects.\n\nLayer \"bottle_glass\": Clear glass bottle standing upright, slightly left of center, ${c.bottleShape}, wall thickness about 3\u20134 mm. Empty exterior silhouette only. Visible Fresnel edge reflections, slight thickness at the lip and base, clean alpha outside the glass. Do not paint the ship inside this layer.\n\nLayer \"ship_hull\": Miniature ${c.shipType} inside the bottle volume only. Wooden hull with aged oak grain, copper or brass fittings, bow facing camera-right. Scale must fit through the neck if the masts were folded. Clean alpha outside the hull.\n\nLayer \"masts_rigging\": Hinged masts raised, tiny brass hinges visible at the mast bases, thread tension lines running up toward the bottle neck as if they were used to raise the masts after insertion. Canvas sails partially set, intricate rope rigging, brass blocks. Confined to the interior of the bottle. Clean alpha elsewhere.\n\nLayer \"sea_resin\": Resin sea filling the bottom of the bottle interior, painted wave texture, subtle surface sheen matching the bottle's interior curvature, hull sitting in the resin. No exterior spill. Clean alpha outside the sea shape.\n\nLighting intent shared across layers: ${c.light}, Rembrandt side light on the ship deck, dust visible only as a later grade, not painted into layers. Cool desaturated base, warm amber on wood and brass.${notesLine(c)}`;\n  }\n\n  function buildSnellcaster(c) {\n    return `Snellcaster refraction pass \u2014 Impossible Bottle glass\n\nInput: LaDe composite (or flattened still with glass mask)\nForeground mesh: bottle_glass layer alpha\nRefractive index \u03b7: 1.52 (soda-lime glass)\nAbsorption: low, slight green tint optional (0.02\u20130.05)\nObject pose: upright bottle, axis vertical, slight three-quarter toward camera\nAuxiliary view: panorama centered at bottle centroid (for unobserved surfaces via refraction)\nRay-warp: apply Snell's Law self-warping each FLUX denoising step\nFresnel blend: edges of glass get reflection bias; interior transmits warped background + ship layers\nOutput: optically-correct refracted scene (masked PSNR target ~16.5, LPIPS ~0.24)\n\nBottle geometry notes: ${c.bottleShape}; wall 3\u20134 mm; match curvature so ship/resin distort realistically.\nLight for refraction consistency: ${c.light}`;\n  }\n\n  function buildHbo(c) {\n    return `[$cinematic-prompt-engine]\nLOOK: HBO prestige drama. Succession restraint mixed with DTF St. Louis grain and Winning Time handmade texture. Not a commercial product shot.\n\nSubject: An impossible bottle on a ${c.table}. A ${c.shipType} sealed inside clear glass (${c.bottleShape}), masts raised on tiny brass hinges, thread lines to the neck, resin sea under the hull.${notesLine(c)}\n\nCamera: Large-format still, 85mm equivalent, eye level, slight three-quarter. Aspect ${c.aspect}. Shallow depth of field. Focus on the glass wall and the ship's midsection. Background falls off softly. No Dutch angle. No macro gimmick.\n\nLighting: ${c.light}. Soft falloff. Rembrandt side light on the ship deck inside the glass. No fill from the opposite side except a faint bounce off the table. Dust in the shaft only where the window light crosses air, not a fog machine. No rim light from behind the bottle.\n\nColor: Cool desaturated base. Saturation pulled back until wood and brass still have a soft electricity. Amber only in the window highlight and brass. Teal only in the oak shadows, never a teal-orange grade. Whites and blacks doubled, but digital sharpness tempered so edges do not crunch.\n\nTexture: Fine film grain, mild halation on the window highlight, slight grease on the oak, honest glass. Handmade, not plastic, not CG, not octane-clean.\n\nRefraction note: the ship and resin must distort through the curved glass according to real thickness. Edges of the bottle show Fresnel. Do not paint a flat ship sticker on the glass.\n\nAnti-slop: no plastic materials, no unmotivated fill, no oversharpen, no HDR glow, no logo, no caption, no extra bottles, no people, no modern objects.\n\nReferences: \"Painterly, motivated, natural lighting, desaturated colors, and lots of depth\" (Six Feet Under); soft electricity + tempered sharpness + grain/halation (DTF St. Louis); grainy, greasy, shiny, handmade (Winning Time).`;\n  }\n\n  function buildTransparent(c) {\n    return `A miniature ${c.shipType} hull and hinged mast rigging assembly only, aged oak grain, brass hinges at mast bases, thread tension lines, canvas sails partially set, intricate rope and blocks, clean edges, isolated subject, transparent background, real alpha channel.${notesLine(c)}\n\n# Critical rules\n- Describe only the subject. Never mention a table, bottle, room, or background.\n- Do not write \"on transparent background\" after naming a surface \u2014 the model may render that surface.\n- Prefer: GPT Image 2 with background=\"transparent\", output_format=\"png\"\n  or Qwen-Image-2.1 with prompt suffix: \"The image has alpha channel and the background is transparent.\"`;\n  }\n\n  function buildSprite(c) {\n    if (c.motion === \"static\") {\n      return `# Motion: static still only \u2014 skip sprite-gen, or run a single-frame atlas for consistency checks.\n\nsprite-gen gen --prompt \"static miniature ${c.shipType} rigging, hinged masts, no motion\" --transparent\n# Optional extract/compose if you need an atlas plate:\n# sprite-gen extract --atlas sprite-sheet.png --output frames/\n# sprite-gen compose-atlas --frames frames/ --output final_atlas.png`;\n    }\n    if (c.motion === \"dust-motes\") {\n      return `# Dust motes drifting in window light shaft (transparent loop)\n\nsprite-gen video-loop --input base_still.png --output loop_frames/\n# Or atlas path:\nsprite-gen gen --prompt \"fine dust particles drifting slowly through a diagonal light shaft, soft bokeh, transparent background\" --transparent\nsprite-gen extract --atlas sprite-sheet.png --output frames/\nsprite-gen compose-atlas --frames frames/ --output dust_atlas.png\n\n# Keep alpha clean: no chroma fringe; verify against white and black.`;\n    }\n    return `# Rigging sway loop (transparent)\n\nsprite-gen video-loop --input base_ship_rigging.png --output loop_frames/\n\n# Atlas path:\nsprite-gen gen --prompt \"miniature ${c.shipType} hinged masts and canvas sails with subtle sway, brass hinges, thread lines, transparent background\" --transparent\nsprite-gen extract --atlas sprite-sheet.png --output frames/\nsprite-gen compose-atlas --frames frames/ --output rigging_atlas.png\n\n# Identity lock: one base still drives all rows; strip chroma to real alpha; verify no fringe on white/black.`;\n  }\n\n  function buildOmni(c) {\n    return `OmniPSD image-to-PSD decomposition (optional refine pass)\n\nInput: LaDe composite or Snellcaster-corrected render\nMode: iterative in-context edit \u2014 progressively extract foreground subjects and erase from canvas to reconstruct editable layers\nPreserve: bottle glass alpha, ship hull, masts/rigging, sea/resin, table, background\nOutput: layered PSD with embedded smart objects\nNotes: only run if LaDe layer count is insufficient; ${c.aspect} canvas; do not merge glass with ship.`;\n  }\n\n  function buildExport() {\n    return `Photoshop import steps\n\n1. File \u2192 Open the LaDe / OmniPSD .psd \u2014 each layer arrives as an embedded smart object.\n2. Confirm layer stack order (top \u2192 bottom): masts_rigging \u00b7 ship_hull \u00b7 sea_resin \u00b7 bottle_glass \u00b7 table \u00b7 background.\n3. Blend modes: bottle_glass \u2192 Normal, opacity ~92\u201396 to read glass; sea_resin \u2192 Normal.\n4. Move glass, ship, and rigging independently. Rigging can be repositioned without touching bottle geometry.\n5. If sprite-gen loop used: File \u2192 Import \u2192 Video Frames to Layers, then convert to Smart Object.\n6. Export master: File \u2192 Export \u2192 Layers to Files (PNG-24 with alpha) for downstream use.`;\n  }\n\n  const BUILDERS = {\n    lade: buildLade, snellcaster: buildSnellcaster, hbo: buildHbo,\n    transparent: buildTransparent, sprite: buildSprite, omni: buildOmni, export: buildExport,\n  };\n\n  function extraFor(stageId, c) {\n    if (stageId === \"lade\") return `<div class=\"extra-card\"><h3>Layer stack</h3><dl class=\"param-grid\"><dt>Layers</dt><dd>6 (variable)</dd><dt>Alpha</dt><dd>RGBA per plate</dd><dt>Aspect</dt><dd>${c.aspect}</dd></dl></div>`;\n    if (stageId === \"snellcaster\") return `<div class=\"extra-card\"><h3>Refraction</h3><dl class=\"param-grid\"><dt>\u03b7 glass</dt><dd>1.52</dd><dt>Wall</dt><dd>3\u20134 mm</dd><dt>PSNR</dt><dd>~16.5</dd><dt>LPIPS</dt><dd>~0.24</dd></dl></div>`;\n    if (stageId === \"hbo\") return `<div class=\"extra-card\"><h3>LOOK card</h3><ul><li>Cool desaturated base</li><li>Doubled whites/blacks</li><li>Grain + halation</li><li>Motivated light only</li></ul></div>`;\n    if (stageId === \"transparent\") return `<div class=\"extra-card\"><h3>Alpha rules</h3><ul><li>Subject only</li><li>GPT Image 2: background=transparent</li><li>Qwen 2.1 alpha suffix</li></ul></div>`;\n    if (stageId === \"sprite\") return `<div class=\"extra-card\"><h3>Motion</h3><p style=\"margin:0;color:var(--text-muted);font-size:.88rem\">${c.motion}</p></div>`;\n    if (stageId === \"omni\") return `<div class=\"extra-card\"><h3>Run when</h3><ul><li>LaDe layer count too coarse</li><li>Glass merged with ship</li></ul></div>`;\n    return \"\";\n  }\n\n  async function pingBackend() {\n    try {\n      const r = await fetch(`${API}/api/health`, { signal: AbortSignal.timeout(1500) });\n      state.backendUp = r.ok;\n      if (r.ok) {\n        const data = await r.json();\n        if (data.comfy) state.checklist.comfy = true;\n      }\n    } catch { state.backendUp = false; }\n    return state.backendUp;\n  }\n\n  async function fetchPrompt(stageId, c) {\n    if (state.backendUp) {\n      try {\n        const r = await fetch(`${API}/api/prompt/${stageId}`, {\n          method: \"POST\",\n          headers: { \"Content-Type\": \"application/json\" },\n          body: JSON.stringify(c),\n        });\n        if (r.ok) {\n          const data = await r.json();\n          if (typeof data.prompt === \"string\") return data.prompt;\n        }\n      } catch {}\n    }\n    const fn = BUILDERS[stageId];\n    return fn ? fn(c) : \"\";\n  }\n\n  async function queueJob(stageId, c) {\n    const stage = STAGES.find(s => s.id === stageId);\n    const body = { stage: stageId, workflow: stage?.workflow || stageId, ...c };\n    const r = await fetch(`${API}/api/generate`, {\n      method: \"POST\",\n      headers: { \"Content-Type\": \"application/json\" },\n      body: JSON.stringify(body),\n    });\n    if (!r.ok) throw new Error(`queue failed: HTTP ${r.status}`);\n    return r.json();\n  }\n\n  async function pollJob(jobId) {\n    const r = await fetch(`${API}/api/job/${jobId}`);\n    if (!r.ok) throw new Error(`poll failed: HTTP ${r.status}`);\n    return r.json();\n  }\n\n  function stopPolling() {\n    if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }\n  }\n\n  async function startJob() {\n    const stage = STAGES[state.stageIndex];\n    if (!stage.workflow) { els.copyStatus.textContent = \"no workflow for this stage\"; return; }\n    if (!(await pingBackend())) { els.copyStatus.textContent = \"backend offline \u2014 local prompt only\"; return; }\n\n    stopPolling();\n    state.job = { id: null, status: \"queuing\", progress: 0 };\n    renderJobStatus();\n\n    try {\n      const { job_id } = await queueJob(stage.id, config());\n      state.job = { id: job_id, status: \"running\", progress: 0 };\n      renderJobStatus();\n\n      const started = Date.now();\n      state.pollTimer = setInterval(async () => {\n        try {\n          const j = await pollJob(job_id);\n          state.job = {\n            id: job_id,\n            status: j.status,\n            progress: j.progress ?? 0,\n            result: j.result,\n            result_prompt: j.result_prompt,\n            error: j.error,\n          };\n          renderJobStatus();\n          if (j.status === \"done\" || j.status === \"error\") {\n            stopPolling();\n            if (j.status === \"done\") {\n              state.stageDone[stage.id] = true;\n              renderNav();\n            }\n          }\n          if (Date.now() - started > COMFY_TIMEOUT_MS) {\n            stopPolling();\n            state.job.status = \"error\";\n            state.job.error = \"timeout\";\n            renderJobStatus();\n          }\n        } catch (e) {\n          stopPolling();\n          state.job = { id: job_id, status: \"error\", error: String(e) };\n          renderJobStatus();\n        }\n      }, COMFY_POLL_MS);\n    } catch (e) {\n      state.job = { id: null, status: \"error\", error: String(e) };\n      renderJobStatus();\n    }\n  }\n\n  function renderJobStatus() {\n    const j = state.job;\n    const box = els.stageExtra;\n    const existing = box.querySelector(\".job-card\");\n    if (existing) existing.remove();\n    if (!j) return;\n\n    const card = document.createElement(\"div\");\n    card.className = \"extra-card job-card\";\n    let body = `<h3>Pipeline job</h3>\n      <dl class=\"param-grid\">\n        <dt>Status</dt><dd>${j.status}</dd>\n        <dt>Job ID</dt><dd>${j.id || \"\u2014\"}</dd>\n        <dt>Progress</dt><dd>${j.progress ?? 0}%</dd>\n      </dl>`;\n\n    if (j.status === \"done\" && j.result) {\n      const url = j.result.image_url || j.result.psd_url;\n      if (url) body += `<img src=\"${url}\" alt=\"result\" style=\"width:100%;border-radius:8px;margin-top:8px\" />`;\n      body += `<div style=\"margin-top:10px;display:flex;gap:8px;flex-wrap:wrap\">\n        ${j.result.psd_url ? `<a class=\"btn secondary\" href=\"${j.result.psd_url}\" download>Download PSD</a>` : \"\"}\n        ${j.result.image_url ? `<a class=\"btn ghost\" href=\"${j.result.image_url}\" download>Download PNG</a>` : \"\"}\n      </div>`;\n    }\n    if (j.status === \"error\") {\n      body += `<p style=\"color:var(--danger);margin:8px 0 0;font-size:.85rem\">${j.error || \"unknown error\"}</p>`;\n    }\n    card.innerHTML = body;\n    box.appendChild(card);\n  }\n\n  function renderNav() {\n    els.nav.innerHTML = \"\";\n    STAGES.forEach((s, i) => {\n      const b = document.createElement(\"button\");\n      b.type = \"button\";\n      b.className = \"stage-tab\";\n      if (i === state.stageIndex) b.classList.add(\"active\");\n      if (state.stageDone[s.id]) b.classList.add(\"done\");\n      b.textContent = s.short;\n      b.addEventListener(\"click\", () => { state.stageIndex = i; render(); });\n      els.nav.appendChild(b);\n    });\n  }\n\n  async function renderStage() {\n    const s = STAGES[state.stageIndex];\n    const c = config();\n\n    els.stageKicker.textContent = `Stage ${s.num}`;\n    els.stageTitle.textContent  = s.title;\n    els.stageDesc.textContent   = s.desc;\n    els.promptLabel.textContent = s.promptLabel;\n    els.promptOutput.textContent = \"\u2026\";\n    els.stageExtra.innerHTML = extraFor(s.id, c);\n    els.copyStatus.textContent = \"\";\n\n    const text = await fetchPrompt(s.id, c);\n    els.promptOutput.textContent = text;\n\n    if (s.workflow) {\n      const runBtn = document.createElement(\"button\");\n      runBtn.type = \"button\";\n      runBtn.className = \"btn secondary\";\n      runBtn.style.marginTop = \"10px\";\n      runBtn.textContent = \"Run stage job\";\n      runBtn.addEventListener(\"click\", startJob);\n      els.stageExtra.appendChild(runBtn);\n    }\n\n    if (state.job) renderJobStatus();\n    els.btnDone.textContent = state.stageDone[s.id] ? \"Mark incomplete\" : \"Mark complete\";\n  }\n\n  function renderChecklist() {\n    els.checklist.innerHTML = \"\";\n    CHECKLIST.forEach((item) => {\n      const li = document.createElement(\"li\");\n      const cb = document.createElement(\"input\");\n      cb.type = \"checkbox\";\n      cb.checked = !!state.checklist[item.id];\n      const span = document.createElement(\"span\");\n      span.textContent = item.label;\n      if (cb.checked) li.classList.add(\"checked\");\n      li.addEventListener(\"click\", (e) => {\n        if (e.target !== cb) cb.checked = !cb.checked;\n        state.checklist[item.id] = cb.checked;\n        li.classList.toggle(\"checked\", cb.checked);\n        saveChecklist();\n        renderProgress();\n      });\n      li.appendChild(cb);\n      li.appendChild(span);\n      els.checklist.appendChild(li);\n    });\n    renderProgress();\n  }\n\n  function renderProgress() {\n    const done = CHECKLIST.filter((i) => state.checklist[i.id]).length;\n    els.progressFill.style.width = `${(done / CHECKLIST.length) * 100}%`;\n    els.progressLabel.textContent = `${done} / ${CHECKLIST.length} ready`;\n  }\n\n  function render() { renderNav(); renderStage(); }\n\n  function loadChecklist() {\n    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || \"{}\").checklist || {}; }\n    catch { return {}; }\n  }\n  function saveChecklist() {\n    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ checklist: state.checklist })); } catch {}\n  }\n\n  async function copyPrompt() {\n    const text = els.promptOutput.textContent || \"\";\n    if (!text.trim()) return;\n    try {\n      await navigator.clipboard.writeText(text);\n    } catch {\n      const r = document.createRange();\n      r.selectNodeContents(els.promptOutput);\n      const sel = window.getSelection();\n      sel.removeAllRanges();\n      sel.addRange(r);\n      document.execCommand(\"copy\");\n    }\n    els.copyStatus.textContent = \"Copied\";\n    setTimeout(() => (els.copyStatus.textContent = \"\"), 1600);\n  }\n\n  function toggleDone() {\n    const s = STAGES[state.stageIndex];\n    state.stageDone[s.id] = !state.stageDone[s.id];\n    els.btnDone.textContent = state.stageDone[s.id] ? \"Mark incomplete\" : \"Mark complete\";\n    renderNav();\n  }\n\n  function resetAll() {\n    if (!confirm(\"Reset checklist and completed stages?\")) return;\n    stopPolling();\n    state.stageDone = {};\n    state.checklist = {};\n    state.job = null;\n    saveChecklist();\n    renderChecklist();\n    render();\n  }\n\n  async function exportPack() {\n    const c = config();\n    const parts = [];\n    for (const s of STAGES) {\n      const text = await fetchPrompt(s.id, c);\n      parts.push(`# ===== Stage ${s.num} \u2014 ${s.title} =====\\n\\n${text}\\n`);\n    }\n    const header = `# Impossible Bottle \u2192 Editable PSD Pipeline\\n# HBO Edition\\n# Generated: ${new Date().toISOString()}\\n\\n## Scene config\\n${JSON.stringify(c, null, 2)}\\n\\n`;\n    const blob = new Blob([header + parts.join(\"\\n\")], { type: \"text/markdown\" });\n    const a = document.createElement(\"a\");\n    a.href = URL.createObjectURL(blob);\n    a.download = \"impossible-bottle-prompt-pack.md\";\n    a.click();\n    URL.revokeObjectURL(a.href);\n  }\n\n  els.form.addEventListener(\"input\", renderStage);\n  els.form.addEventListener(\"change\", renderStage);\n  els.btnCopy.addEventListener(\"click\", copyPrompt);\n  els.btnDone.addEventListener(\"click\", toggleDone);\n  els.btnReset.addEventListener(\"click\", resetAll);\n  els.btnExport.addEventListener(\"click\", exportPack);\n\n  (async () => {\n    await pingBackend();\n    renderChecklist();\n    render();\n  })();\n})();\n\n</script>\n</body>\n</html>\n")

@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(HTML_PAGE)

if __name__ == "__main__":
    import uvicorn
    mode = "ComfyUI" if USE_COMFY else "simulated"
    print(f"\n  Impossible Bottle → Editable PSD Pipeline\n  http://localhost:{PORT}\n  mode: {mode}\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
