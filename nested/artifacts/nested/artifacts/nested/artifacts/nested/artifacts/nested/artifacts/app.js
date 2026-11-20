(function () {
  "use strict";

  const API = ""; // same-origin; set to "http://127.0.0.1:8000" if served elsewhere
  const COMFY_POLL_MS = 1500;
  const COMFY_TIMEOUT_MS = 20 * 60 * 1000;

  const STAGES = [
    { id: "lade",        num: 1, title: "Layered generation · LaDe",        short: "1 · LaDe",        desc: "Flexible semantic RGBA layers from a single structured prompt.", promptLabel: "LaDe tokens",           workflow: "lade" },
    { id: "snellcaster", num: 2, title: "Refraction physics · Snellcaster", short: "2 · Snellcaster", desc: "Training-free Snell's Law ray-warping on the glass layer.",       promptLabel: "Snellcaster parameters", workflow: "snellcaster" },
    { id: "hbo",         num: 3, title: "Cinematic grade · HBO LOOK",       short: "3 · HBO LOOK",    desc: "DP-inspired LOOK card.",                                          promptLabel: "HBO LOOK card",         workflow: "hbo" },
    { id: "transparent", num: 4, title: "Transparent elements",             short: "4 · Alpha",       desc: "Native RGBA generation for isolatable plates.",                   promptLabel: "Transparent subject prompt", workflow: "transparent" },
    { id: "sprite",      num: 5, title: "Motion frames · sprite-gen",       short: "5 · Motion",      desc: "Still → transparent motion loops or atlas.",                      promptLabel: "sprite-gen commands",   workflow: "sprite" },
    { id: "omni",        num: 6, title: "Layer refinement · OmniPSD",       short: "6 · OmniPSD",     desc: "Optional image-to-PSD decomposition.",                            promptLabel: "OmniPSD notes",         workflow: "omni" },
    { id: "export",      num: 7, title: "Export · Photoshop",               short: "7 · PSD",         desc: "Smart-object layered PSD.",                                       promptLabel: "Photoshop import steps", workflow: null },
  ];

  const CHECKLIST = [
    { id: "lade",      label: "LaDe cloned + deps installed" },
    { id: "snell",     label: "Snellcaster cloned + FLUX weights" },
    { id: "cinematic", label: "AI_Cinematic_Prompt / LOOK card ready" },
    { id: "alpha",     label: "GPT Image 2 key or Qwen-Image-2.1 weights" },
    { id: "sprite",    label: "sprite-gen CLI installed + tested" },
    { id: "omni",      label: "OmniPSD cloned (optional refine)" },
    { id: "comfy",     label: "ComfyUI running on :8188" },
    { id: "ps",        label: "Photoshop ready for smart objects" },
  ];

  const STORAGE_KEY = "ib.pipeline.v1";

  const state = {
    stageIndex: 0,
    stageDone: {},
    checklist: loadChecklist(),
    job: null,
    pollTimer: null,
    backendUp: false,
  };

  const els = {
    nav:          document.getElementById("stages-nav"),
    form:         document.getElementById("config-form"),
    stageKicker:  document.getElementById("stage-kicker"),
    stageTitle:   document.getElementById("stage-title"),
    stageDesc:    document.getElementById("stage-desc"),
    promptLabel:  document.getElementById("prompt-label"),
    promptOutput: document.getElementById("prompt-output"),
    stageExtra:   document.getElementById("stage-extra"),
    copyStatus:   document.getElementById("copy-status"),
    checklist:    document.getElementById("checklist"),
    progressFill: document.getElementById("progress-fill"),
    progressLabel:document.getElementById("progress-label"),
    btnCopy:      document.getElementById("btn-copy-prompt"),
    btnDone:      document.getElementById("btn-mark-done"),
    btnReset:     document.getElementById("btn-reset"),
    btnExport:    document.getElementById("btn-export-pack"),
  };

  function config() {
    const fd = new FormData(els.form);
    return {
      bottleShape: fd.get("bottleShape") || "classic round, long neck",
      shipType:    fd.get("shipType")    || "19th-century brig",
      table:       fd.get("table")       || "dark oak table, grain left-to-right, worn finish",
      light:       fd.get("light")       || "motivated natural window light from camera left",
      aspect:      fd.get("aspect")      || "3:2",
      motion:      fd.get("motion")      || "static",
      notes:       (fd.get("notes") || "").trim(),
    };
  }
  const notesLine = (c) => (c.notes ? `\nExtra: ${c.notes}` : "");

  function buildLade(c) {
    return `Create a multi-layer RGBA design of a physically plausible Impossible Bottle still life. Flexible layer count, each layer a semantically independent RGBA plate with clean alpha. No text, no watermarks, no logos.

Canvas: ${c.aspect}, large-format still, shallow depth of field.

Layer "table": ${c.table}, deep teal shadows in the grain, warm amber highlight rolloff where window light hits, fine film grain. No objects.

Layer "bottle_glass": Clear glass bottle standing upright, slightly left of center, ${c.bottleShape}, wall thickness about 3–4 mm. Empty exterior silhouette only. Visible Fresnel edge reflections, slight thickness at the lip and base, clean alpha outside the glass. Do not paint the ship inside this layer.

Layer "ship_hull": Miniature ${c.shipType} inside the bottle volume only. Wooden hull with aged oak grain, copper or brass fittings, bow facing camera-right. Scale must fit through the neck if the masts were folded. Clean alpha outside the hull.

Layer "masts_rigging": Hinged masts raised, tiny brass hinges visible at the mast bases, thread tension lines running up toward the bottle neck as if they were used to raise the masts after insertion. Canvas sails partially set, intricate rope rigging, brass blocks. Confined to the interior of the bottle. Clean alpha elsewhere.

Layer "sea_resin": Resin sea filling the bottom of the bottle interior, painted wave texture, subtle surface sheen matching the bottle's interior curvature, hull sitting in the resin. No exterior spill. Clean alpha outside the sea shape.

Lighting intent shared across layers: ${c.light}, Rembrandt side light on the ship deck, dust visible only as a later grade, not painted into layers. Cool desaturated base, warm amber on wood and brass.${notesLine(c)}`;
  }

  function buildSnellcaster(c) {
    return `Snellcaster refraction pass — Impossible Bottle glass

Input: LaDe composite (or flattened still with glass mask)
Foreground mesh: bottle_glass layer alpha
Refractive index η: 1.52 (soda-lime glass)
Absorption: low, slight green tint optional (0.02–0.05)
Object pose: upright bottle, axis vertical, slight three-quarter toward camera
Auxiliary view: panorama centered at bottle centroid (for unobserved surfaces via refraction)
Ray-warp: apply Snell's Law self-warping each FLUX denoising step
Fresnel blend: edges of glass get reflection bias; interior transmits warped background + ship layers
Output: optically-correct refracted scene (masked PSNR target ~16.5, LPIPS ~0.24)

Bottle geometry notes: ${c.bottleShape}; wall 3–4 mm; match curvature so ship/resin distort realistically.
Light for refraction consistency: ${c.light}`;
  }

  function buildHbo(c) {
    return `[$cinematic-prompt-engine]
LOOK: HBO prestige drama. Succession restraint mixed with DTF St. Louis grain and Winning Time handmade texture. Not a commercial product shot.

Subject: An impossible bottle on a ${c.table}. A ${c.shipType} sealed inside clear glass (${c.bottleShape}), masts raised on tiny brass hinges, thread lines to the neck, resin sea under the hull.${notesLine(c)}

Camera: Large-format still, 85mm equivalent, eye level, slight three-quarter. Aspect ${c.aspect}. Shallow depth of field. Focus on the glass wall and the ship's midsection. Background falls off softly. No Dutch angle. No macro gimmick.

Lighting: ${c.light}. Soft falloff. Rembrandt side light on the ship deck inside the glass. No fill from the opposite side except a faint bounce off the table. Dust in the shaft only where the window light crosses air, not a fog machine. No rim light from behind the bottle.

Color: Cool desaturated base. Saturation pulled back until wood and brass still have a soft electricity. Amber only in the window highlight and brass. Teal only in the oak shadows, never a teal-orange grade. Whites and blacks doubled, but digital sharpness tempered so edges do not crunch.

Texture: Fine film grain, mild halation on the window highlight, slight grease on the oak, honest glass. Handmade, not plastic, not CG, not octane-clean.

Refraction note: the ship and resin must distort through the curved glass according to real thickness. Edges of the bottle show Fresnel. Do not paint a flat ship sticker on the glass.

Anti-slop: no plastic materials, no unmotivated fill, no oversharpen, no HDR glow, no logo, no caption, no extra bottles, no people, no modern objects.

References: "Painterly, motivated, natural lighting, desaturated colors, and lots of depth" (Six Feet Under); soft electricity + tempered sharpness + grain/halation (DTF St. Louis); grainy, greasy, shiny, handmade (Winning Time).`;
  }

  function buildTransparent(c) {
    return `A miniature ${c.shipType} hull and hinged mast rigging assembly only, aged oak grain, brass hinges at mast bases, thread tension lines, canvas sails partially set, intricate rope and blocks, clean edges, isolated subject, transparent background, real alpha channel.${notesLine(c)}

# Critical rules
- Describe only the subject. Never mention a table, bottle, room, or background.
- Do not write "on transparent background" after naming a surface — the model may render that surface.
- Prefer: GPT Image 2 with background="transparent", output_format="png"
  or Qwen-Image-2.1 with prompt suffix: "The image has alpha channel and the background is transparent."`;
  }

  function buildSprite(c) {
    if (c.motion === "static") {
      return `# Motion: static still only — skip sprite-gen, or run a single-frame atlas for consistency checks.

sprite-gen gen --prompt "static miniature ${c.shipType} rigging, hinged masts, no motion" --transparent
# Optional extract/compose if you need an atlas plate:
# sprite-gen extract --atlas sprite-sheet.png --output frames/
# sprite-gen compose-atlas --frames frames/ --output final_atlas.png`;
    }
    if (c.motion === "dust-motes") {
      return `# Dust motes drifting in window light shaft (transparent loop)

sprite-gen video-loop --input base_still.png --output loop_frames/
# Or atlas path:
sprite-gen gen --prompt "fine dust particles drifting slowly through a diagonal light shaft, soft bokeh, transparent background" --transparent
sprite-gen extract --atlas sprite-sheet.png --output frames/
sprite-gen compose-atlas --frames frames/ --output dust_atlas.png

# Keep alpha clean: no chroma fringe; verify against white and black.`;
    }
    return `# Rigging sway loop (transparent)

sprite-gen video-loop --input base_ship_rigging.png --output loop_frames/

# Atlas path:
sprite-gen gen --prompt "miniature ${c.shipType} hinged masts and canvas sails with subtle sway, brass hinges, thread lines, transparent background" --transparent
sprite-gen extract --atlas sprite-sheet.png --output frames/
sprite-gen compose-atlas --frames frames/ --output rigging_atlas.png

# Identity lock: one base still drives all rows; strip chroma to real alpha; verify no fringe on white/black.`;
  }

  function buildOmni(c) {
    return `OmniPSD image-to-PSD decomposition (optional refine pass)

Input: LaDe composite or Snellcaster-corrected render
Mode: iterative in-context edit — progressively extract foreground subjects and erase from canvas to reconstruct editable layers
Preserve: bottle glass alpha, ship hull, masts/rigging, sea/resin, table, background
Output: layered PSD with embedded smart objects
Notes: only run if LaDe layer count is insufficient; ${c.aspect} canvas; do not merge glass with ship.`;
  }

  function buildExport() {
    return `Photoshop import steps

1. File → Open the LaDe / OmniPSD .psd — each layer arrives as an embedded smart object.
2. Confirm layer stack order (top → bottom): masts_rigging · ship_hull · sea_resin · bottle_glass · table · background.
3. Blend modes: bottle_glass → Normal, opacity ~92–96 to read glass; sea_resin → Normal.
4. Move glass, ship, and rigging independently. Rigging can be repositioned without touching bottle geometry.
5. If sprite-gen loop used: File → Import → Video Frames to Layers, then convert to Smart Object.
6. Export master: File → Export → Layers to Files (PNG-24 with alpha) for downstream use.`;
  }

  const BUILDERS = {
    lade: buildLade, snellcaster: buildSnellcaster, hbo: buildHbo,
    transparent: buildTransparent, sprite: buildSprite, omni: buildOmni, export: buildExport,
  };

  function extraFor(stageId, c) {
    if (stageId === "lade") return `<div class="extra-card"><h3>Layer stack</h3><dl class="param-grid"><dt>Layers</dt><dd>6 (variable)</dd><dt>Alpha</dt><dd>RGBA per plate</dd><dt>Aspect</dt><dd>${c.aspect}</dd></dl></div>`;
    if (stageId === "snellcaster") return `<div class="extra-card"><h3>Refraction</h3><dl class="param-grid"><dt>η glass</dt><dd>1.52</dd><dt>Wall</dt><dd>3–4 mm</dd><dt>PSNR</dt><dd>~16.5</dd><dt>LPIPS</dt><dd>~0.24</dd></dl></div>`;
    if (stageId === "hbo") return `<div class="extra-card"><h3>LOOK card</h3><ul><li>Cool desaturated base</li><li>Doubled whites/blacks</li><li>Grain + halation</li><li>Motivated light only</li></ul></div>`;
    if (stageId === "transparent") return `<div class="extra-card"><h3>Alpha rules</h3><ul><li>Subject only</li><li>GPT Image 2: background=transparent</li><li>Qwen 2.1 alpha suffix</li></ul></div>`;
    if (stageId === "sprite") return `<div class="extra-card"><h3>Motion</h3><p style="margin:0;color:var(--text-muted);font-size:.88rem">${c.motion}</p></div>`;
    if (stageId === "omni") return `<div class="extra-card"><h3>Run when</h3><ul><li>LaDe layer count too coarse</li><li>Glass merged with ship</li></ul></div>`;
    return "";
  }

  async function pingBackend() {
    try {
      const r = await fetch(`${API}/api/health`, { signal: AbortSignal.timeout(1500) });
      state.backendUp = r.ok;
      if (r.ok) {
        const data = await r.json();
        if (data.comfy) state.checklist.comfy = true;
      }
    } catch { state.backendUp = false; }
    return state.backendUp;
  }

  async function fetchPrompt(stageId, c) {
    if (state.backendUp) {
      try {
        const r = await fetch(`${API}/api/prompt/${stageId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(c),
        });
        if (r.ok) {
          const data = await r.json();
          if (typeof data.prompt === "string") return data.prompt;
        }
      } catch {}
    }
    const fn = BUILDERS[stageId];
    return fn ? fn(c) : "";
  }

  async function queueJob(stageId, c) {
    const stage = STAGES.find(s => s.id === stageId);
    const body = { stage: stageId, workflow: stage?.workflow || stageId, ...c };
    const r = await fetch(`${API}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`queue failed: HTTP ${r.status}`);
    return r.json();
  }

  async function pollJob(jobId) {
    const r = await fetch(`${API}/api/job/${jobId}`);
    if (!r.ok) throw new Error(`poll failed: HTTP ${r.status}`);
    return r.json();
  }

  function stopPolling() {
    if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
  }

  async function startJob() {
    const stage = STAGES[state.stageIndex];
    if (!stage.workflow) { els.copyStatus.textContent = "no workflow for this stage"; return; }
    if (!(await pingBackend())) { els.copyStatus.textContent = "backend offline — local prompt only"; return; }

    stopPolling();
    state.job = { id: null, status: "queuing", progress: 0 };
    renderJobStatus();

    try {
      const { job_id } = await queueJob(stage.id, config());
      state.job = { id: job_id, status: "running", progress: 0 };
      renderJobStatus();

      const started = Date.now();
      state.pollTimer = setInterval(async () => {
        try {
          const j = await pollJob(job_id);
          state.job = {
            id: job_id,
            status: j.status,
            progress: j.progress ?? 0,
            result: j.result,
            result_prompt: j.result_prompt,
            error: j.error,
          };
          renderJobStatus();
          if (j.status === "done" || j.status === "error") {
            stopPolling();
            if (j.status === "done") {
              state.stageDone[stage.id] = true;
              renderNav();
            }
          }
          if (Date.now() - started > COMFY_TIMEOUT_MS) {
            stopPolling();
            state.job.status = "error";
            state.job.error = "timeout";
            renderJobStatus();
          }
        } catch (e) {
          stopPolling();
          state.job = { id: job_id, status: "error", error: String(e) };
          renderJobStatus();
        }
      }, COMFY_POLL_MS);
    } catch (e) {
      state.job = { id: null, status: "error", error: String(e) };
      renderJobStatus();
    }
  }

  function renderJobStatus() {
    const j = state.job;
    const box = els.stageExtra;
    const existing = box.querySelector(".job-card");
    if (existing) existing.remove();
    if (!j) return;

    const card = document.createElement("div");
    card.className = "extra-card job-card";
    let body = `<h3>Pipeline job</h3>
      <dl class="param-grid">
        <dt>Status</dt><dd>${j.status}</dd>
        <dt>Job ID</dt><dd>${j.id || "—"}</dd>
        <dt>Progress</dt><dd>${j.progress ?? 0}%</dd>
      </dl>`;

    if (j.status === "done" && j.result) {
      const url = j.result.image_url || j.result.psd_url;
      if (url) body += `<img src="${url}" alt="result" style="width:100%;border-radius:8px;margin-top:8px" />`;
      body += `<div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
        ${j.result.psd_url ? `<a class="btn secondary" href="${j.result.psd_url}" download>Download PSD</a>` : ""}
        ${j.result.image_url ? `<a class="btn ghost" href="${j.result.image_url}" download>Download PNG</a>` : ""}
      </div>`;
    }
    if (j.status === "error") {
      body += `<p style="color:var(--danger);margin:8px 0 0;font-size:.85rem">${j.error || "unknown error"}</p>`;
    }
    card.innerHTML = body;
    box.appendChild(card);
  }

  function renderNav() {
    els.nav.innerHTML = "";
    STAGES.forEach((s, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "stage-tab";
      if (i === state.stageIndex) b.classList.add("active");
      if (state.stageDone[s.id]) b.classList.add("done");
      b.textContent = s.short;
      b.addEventListener("click", () => { state.stageIndex = i; render(); });
      els.nav.appendChild(b);
    });
  }

  async function renderStage() {
    const s = STAGES[state.stageIndex];
    const c = config();

    els.stageKicker.textContent = `Stage ${s.num}`;
    els.stageTitle.textContent  = s.title;
    els.stageDesc.textContent   = s.desc;
    els.promptLabel.textContent = s.promptLabel;
    els.promptOutput.textContent = "…";
    els.stageExtra.innerHTML = extraFor(s.id, c);
    els.copyStatus.textContent = "";

    const text = await fetchPrompt(s.id, c);
    els.promptOutput.textContent = text;

    if (s.workflow) {
      const runBtn = document.createElement("button");
      runBtn.type = "button";
      runBtn.className = "btn secondary";
      runBtn.style.marginTop = "10px";
      runBtn.textContent = "Run stage job";
      runBtn.addEventListener("click", startJob);
      els.stageExtra.appendChild(runBtn);
    }

    if (state.job) renderJobStatus();
    els.btnDone.textContent = state.stageDone[s.id] ? "Mark incomplete" : "Mark complete";
  }

  function renderChecklist() {
    els.checklist.innerHTML = "";
    CHECKLIST.forEach((item) => {
      const li = document.createElement("li");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !!state.checklist[item.id];
      const span = document.createElement("span");
      span.textContent = item.label;
      if (cb.checked) li.classList.add("checked");
      li.addEventListener("click", (e) => {
        if (e.target !== cb) cb.checked = !cb.checked;
        state.checklist[item.id] = cb.checked;
        li.classList.toggle("checked", cb.checked);
        saveChecklist();
        renderProgress();
      });
      li.appendChild(cb);
      li.appendChild(span);
      els.checklist.appendChild(li);
    });
    renderProgress();
  }

  function renderProgress() {
    const done = CHECKLIST.filter((i) => state.checklist[i.id]).length;
    els.progressFill.style.width = `${(done / CHECKLIST.length) * 100}%`;
    els.progressLabel.textContent = `${done} / ${CHECKLIST.length} ready`;
  }

  function render() { renderNav(); renderStage(); }

  function loadChecklist() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}").checklist || {}; }
    catch { return {}; }
  }
  function saveChecklist() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ checklist: state.checklist })); } catch {}
  }

  async function copyPrompt() {
    const text = els.promptOutput.textContent || "";
    if (!text.trim()) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const r = document.createRange();
      r.selectNodeContents(els.promptOutput);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(r);
      document.execCommand("copy");
    }
    els.copyStatus.textContent = "Copied";
    setTimeout(() => (els.copyStatus.textContent = ""), 1600);
  }

  function toggleDone() {
    const s = STAGES[state.stageIndex];
    state.stageDone[s.id] = !state.stageDone[s.id];
    els.btnDone.textContent = state.stageDone[s.id] ? "Mark incomplete" : "Mark complete";
    renderNav();
  }

  function resetAll() {
    if (!confirm("Reset checklist and completed stages?")) return;
    stopPolling();
    state.stageDone = {};
    state.checklist = {};
    state.job = null;
    saveChecklist();
    renderChecklist();
    render();
  }

  async function exportPack() {
    const c = config();
    const parts = [];
    for (const s of STAGES) {
      const text = await fetchPrompt(s.id, c);
      parts.push(`# ===== Stage ${s.num} — ${s.title} =====\n\n${text}\n`);
    }
    const header = `# Impossible Bottle → Editable PSD Pipeline\n# HBO Edition\n# Generated: ${new Date().toISOString()}\n\n## Scene config\n${JSON.stringify(c, null, 2)}\n\n`;
    const blob = new Blob([header + parts.join("\n")], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "impossible-bottle-prompt-pack.md";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  els.form.addEventListener("input", renderStage);
  els.form.addEventListener("change", renderStage);
  els.btnCopy.addEventListener("click", copyPrompt);
  els.btnDone.addEventListener("click", toggleDone);
  els.btnReset.addEventListener("click", resetAll);
  els.btnExport.addEventListener("click", exportPack);

  (async () => {
    await pingBackend();
    renderChecklist();
    render();
  })();
})();
