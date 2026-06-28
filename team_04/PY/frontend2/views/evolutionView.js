// Design Evolution + Decision Tree view. Renders the optimization path (candidates
// over generations), the decision tree (generation -> strategy -> best), rejected
// options, and the final selection — from the orchestrator's evolution payload.

let data = null;

export function activate() {
  render();
}

export async function onAction(payload) {
  if (payload.action === "render") {
    data = payload;
    render();
  }
}

function fmtScore(s) { const n = Number(s); return Number.isFinite(n) ? n.toFixed(2) : "—"; }
function isFailed(e) { return e.status === "invalid" || e.status === "rejected" || e.valid === false; }

function render() {
  const root = document.getElementById("evolution-scroll");
  if (!root) return;
  root.dataset.ready = "1";
  if (!data) {
    root.innerHTML = `<div class="center-empty"><div class="big">🌳</div><div>Run a design, optimize, then export to view evolution.</div></div>`;
    return;
  }

  const history = data.history || [];
  const best = data.best || [];
  const accepted = data.accepted_option_id;

  // group history by generation for the timeline + tree
  const byGen = {};
  history.forEach((e) => {
    const g = e.generation ?? 0;
    (byGen[g] = byGen[g] || []).push(e);
  });
  const gens = Object.keys(byGen).map(Number).sort((a, b) => a - b);

  const timeline = history.length
    ? history.slice(0, 60).map((e, i) => {
        const cls = isFailed(e) ? "evo-node rejected" : "evo-node";
        return `<div class="${cls}">
          <div>#${e.iteration ?? i + 1} · ${(e.shape_type || "candidate").replace(/_/g, " ")}</div>
          <div class="score">${fmtScore(e.score)}</div>
          <div style="color:var(--text-dim);font-size:11px;">${e.strategy || ""}</div>
        </div>`;
      }).join("")
    : `<div class="tree-empty">No optimization history recorded.</div>`;

  const tree = gens.length
    ? gens.map((g) => {
        const entries = byGen[g];
        const bestInGen = entries.filter((e) => !isFailed(e)).sort((a, b) => (b.score || 0) - (a.score || 0))[0];
        const rejectedCount = entries.filter(isFailed).length;
        return `<div class="evo-node ${bestInGen ? "best" : ""}">
          <div><strong>Generation ${g}</strong></div>
          <div>${entries.length} candidates · ${rejectedCount} rejected</div>
          <div class="score">best ${fmtScore(bestInGen?.score)}</div>
        </div>`;
      }).join('<div style="align-self:center;color:var(--text-dim);">→</div>')
    : `<div class="tree-empty">Decision tree builds from optimization generations.</div>`;

  const finalSel = best.map((o, i) => {
    const isAccepted = o.option_id === accepted;
    return `<div class="evo-node ${isAccepted ? "best" : ""}">
      <div>Option ${i + 1}${isAccepted ? " ✓ selected" : ""}</div>
      <div class="score">${fmtScore(o.score)}</div>
      <div style="color:var(--text-dim);font-size:11px;">${(o.shape_type || "").replace(/_/g, " ")} · ${Math.round(o.height || 0)}m</div>
    </div>`;
  }).join("");

  const rejected = data.rejected
    ? `<div class="evo-node rejected"><div>Rejected edit</div><div style="color:var(--text-dim);font-size:11px;">${(data.rejected.shape_type || "").replace(/_/g, " ")}</div></div>`
    : `<div class="tree-empty">No rejected edits.</div>`;

  root.innerHTML = `
    <h2 style="margin:0 0 6px;color:var(--text-bright);font-size:18px;">Design Evolution</h2>
    <p style="margin:0 0 20px;color:var(--text-dim);font-size:13px;">
      Top score ${fmtScore(data.score)} · ${history.length} candidates explored across ${gens.length} generation(s).
    </p>
    <div class="evo-wrap">
      <div class="evo-section"><h3>Decision Tree</h3><div class="evo-timeline">${tree}</div></div>
      <div class="evo-section"><h3>Final Selection</h3><div class="evo-timeline">${finalSel || '<div class="tree-empty">No options.</div>'}</div></div>
      <div class="evo-section"><h3>Rejected</h3><div class="evo-timeline">${rejected}</div></div>
      <div class="evo-section"><h3>Optimization Path</h3><div class="evo-timeline">${timeline}</div></div>
    </div>`;
}
