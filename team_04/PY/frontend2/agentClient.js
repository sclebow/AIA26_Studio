// Backend B (Team-04 Agent API) client — the notebook-validated agent workflow.
//
// Drives: create/reuse a session, stream the agent chat over SSE, and keep the
// store's decision graph, explorer tree, traces and agent state in sync from the
// real backend responses. Nothing here mocks geometry or fabricates a trace —
// every value comes from a /sessions/* response.
//
// SSE event contract (team_04/backend/routers/chat.py):
//   token    — partial assistant text
//   tool     — {name, input_preview} a tool call fired
//   decision — a decision-graph node {node_id, type, label, parent_id, is_selected}
//   state    — final AgentState {placed_buildings, site_boundary, violations, …}
//   error    — error string
//   done     — stream finished

import { api } from "./core/api.js";
import {
  getState,
  setState,
  pushMessage,
  pushError,
  setLoading,
  setStatus,
} from "./core/store.js";

// Probe Backend B once; cache the result on the store so views can fall back.
export async function ensureAgentAvailable() {
  const s = getState();
  if (s.agentAvailable !== null) return s.agentAvailable;
  try {
    await api.agent.ping();
    setState({ agentAvailable: true });
    return true;
  } catch (err) {
    setState({ agentAvailable: false });
    pushError(`Agent backend unreachable at ${api.agentBase || "same origin"}: ${err.message}`);
    return false;
  }
}

// Create a session if we don't have one. layout_payload feeds build_initial_state
// (user_prompt, site_boundary, building_intents, requested_positions, …).
export async function ensureSession(layoutPayload = {}) {
  const s = getState();
  if (s.sessionId) return s.sessionId;
  setLoading("sessions", true);
  try {
    const { session_id } = await api.agent.createSession(layoutPayload);
    setState({ sessionId: session_id });
    return session_id;
  } finally {
    setLoading("sessions", false);
  }
}

// Pull the decision graph for the current session into the store.
export async function refreshDecisionGraph() {
  const { sessionId } = getState();
  if (!sessionId) return null;
  setLoading("decisions", true);
  try {
    const graph = await api.agent.getDecisionGraph(sessionId);
    setState({ decisionGraph: graph || { nodes: [], edges: [], head: null } });
    return graph;
  } catch (err) {
    pushError(`Decision graph load failed: ${err.message}`);
    return null;
  } finally {
    setLoading("decisions", false);
  }
}

// Map a real backend BuildingInfo (boundary[[x,y]], placement_options[]) into the
// flat option shape the Three.js viewer + compare table already consume
// (footprint, height, score, shape_type, constraint_report.metrics). This is a
// pure projection of backend data — no geometry is invented; missing metrics stay
// absent rather than being faked.
function buildingToViewerOptions(buildings, explorerSite) {
  const options = [];
  const shapesByType = {};
  const siteArea = explorerSite?.area_sqm || null;

  buildings.forEach((b, bi) => {
    const baseFootprint = (b.boundary || []).map((p) => [Number(p[0]), Number(p[1])]);
    const opts =
      (b.placement_options && b.placement_options.length)
        ? b.placement_options
        : [{ option_id: b.building_id, boundary: b.boundary, rank: 1 }];

    opts.forEach((o, oi) => {
      const footprint = (o.boundary && o.boundary.length ? o.boundary : baseFootprint).map(
        (p) => [Number(p[0]), Number(p[1])]
      );
      if (footprint.length < 3) return;
      const fpArea = Math.abs(polyArea(footprint));
      const opt = {
        option_id: o.option_id || `${b.building_id}_opt_${oi + 1}`,
        building_id: b.building_id,
        shape_type: b.building_type || b.shape_type || "building",
        footprint,
        height: b.height_m || 12,
        floors: b.height_m ? Math.max(1, Math.round(b.height_m / 3)) : 0,
        rotation_degrees: o.rotation_degrees || 0,
        // These are GENERATION placement candidates, not view-optimization results,
        // so they carry no combined_score. The Optimization panel reads scored
        // options from optimizationResult; here score is left null (not 0) to avoid
        // showing fake "0.00" scores.
        score: o.combined_score ?? null,
        rank: o.rank ?? oi + 1,
        placement_only: o.combined_score == null,
        status: o.fits_within_site === false ? "invalid" : "candidate",
        // Real metrics from the backend; FAR derived from area only when site
        // area is known. Anything unknown is omitted, not zero-filled.
        constraint_report: {
          passed: o.fits_within_site !== false,
          metrics: {
            footprint_area: Math.round(fpArea),
            ...(siteArea ? { far: +(fpArea / siteArea).toFixed(3) } : {}),
            ...(o.combined_score != null ? { combined_score: o.combined_score } : {}),
            ...(o.unblocked_view_score != null
              ? { unblocked_view_score: o.unblocked_view_score }
              : {}),
            ...(o.outside_area_sqm != null ? { outside_area_sqm: o.outside_area_sqm } : {}),
          },
        },
      };
      options.push(opt);
      const t = opt.shape_type;
      (shapesByType[t] = shapesByType[t] || []).push(opt);
    });
  });

  return { options, shapesByType };
}

function polyArea(fp) {
  let a = 0;
  for (let i = 0; i < fp.length; i++) {
    const j = (i + 1) % fp.length;
    a += fp[i][0] * fp[j][1] - fp[j][0] * fp[i][1];
  }
  return a / 2;
}

// Pull the explorer tree (site + buildings + wings + placement options) and
// project it into the viewer/compare option model so the 3D viewer renders the
// REAL agent geometry.
export async function refreshExplorer() {
  const { sessionId } = getState();
  if (!sessionId) return null;
  setLoading("explorer", true);
  try {
    const tree = await api.agent.getExplorer(sessionId);
    const buildings = tree?.buildings || [];
    const explorerSite = tree?.site || null;
    const { options, shapesByType } = buildingToViewerOptions(buildings, explorerSite);

    // Saved manipulated shapes (Shape Library versions) for the left-panel
    // "Saved Shapes" explorer — best-effort, never blocks the tree refresh.
    let savedShapes = getState().savedShapes || [];
    try {
      const sv = await api.agent.listDesignOptions(sessionId);
      savedShapes = sv?.options || [];
    } catch { /* no saved shapes yet / endpoint optional */ }

    // Persisted OPTIMIZED options (from "Optimize selected saved shapes") — reloaded so
    // they survive a page refresh and stay browsable/comparable in the Optimization
    // explorer. Each record carries geometry + metrics, so it previews like a live option.
    let savedOptimized = getState().savedOptimized || [];
    try {
      const oh = await api.agent.optimizationHistory(sessionId);
      const hist = oh?.optimization_history || [];
      // de-duplicate by optimized_option_id (keep the latest run of each)
      const byId = new Map();
      for (const h of hist) if (h.optimized_option_id) byId.set(h.optimized_option_id, h);
      savedOptimized = [...byId.values()].map((h) => ({
        option_id: h.optimized_option_id,
        label: h.optimized_option_id,
        shape_type: h.shape_type,
        source_shape_option_id: h.source_shape_option_id,
        variant_tag: h.variant_tag,
        boundary: h.geometry?.boundary || [],
        footprint: h.geometry?.boundary || [],
        holes: h.geometry?.holes || [],
        floor_plates: h.geometry?.floor_plates || [],
        floors: h.geometry?.floors,
        score: h.overall_score,
        objective_scores: h.objective_scores || h.metrics || {},
        rotation_degrees: h.rotation,
        is_optimized: true,
      }));
    } catch { /* no optimization history yet / endpoint optional */ }

    const patch = {
      explorerSite,
      buildings,
      shapesByType,
      savedShapes,
      savedOptimized,
    };
    // Only overwrite the live option set when the backend actually has geometry,
    // so an empty refresh never blanks an in-progress viewer. Do NOT clobber real
    // optimization results (optimizationResult set) with generation footprints.
    if (options.length && !getState().optimizationResult) {
      patch.options = options;
      patch.comparisonOptions = options;
      patch.visibleOptionIds = new Set(options.map((o) => o.option_id));
      // Feed the real site boundary into the viewer's `site` field.
      if (explorerSite?.boundary) {
        patch.site = {
          ...(getState().site || {}),
          boundary: explorerSite.boundary.map((p) => [Number(p[0]), Number(p[1])]),
          site_area: explorerSite.area_sqm,
        };
      }
    }
    setState(patch);

    // Re-render the 3D viewer when geometry arrives — buildings (pickable for the
    // tools) OR optimization options — if the viewer is the active view.
    if ((options.length || buildings.length) && getState().centerView === "viewer") {
      try {
        const viewer = await import("./views/viewerView.js");
        viewer.activate();
      } catch {
        /* viewer not mounted yet — activate() will run when it is */
      }
    }
    return tree;
  } catch (err) {
    pushError(`Explorer load failed: ${err.message}`);
    return null;
  } finally {
    setLoading("explorer", false);
  }
}

// Trigger a real geometry export (GeoJSON or JSON) for the active session by
// opening the backend download route. No file is fabricated client-side — the
// browser downloads exactly what /export/{id}/... serves from session state.
export function exportSession(format = "geojson") {
  const { sessionId } = getState();
  if (!sessionId) {
    pushError("No active session to export. Place a building first.");
    return false;
  }
  const url =
    format === "json" ? api.agent.exportJsonUrl(sessionId) : api.agent.exportGeojsonUrl(sessionId);
  window.open(url, "_blank");
  return true;
}

// Select a Pareto / branch node, then refresh the graph so the new head + the
// appended 'select' node show up. Returns the backend's select response.
export async function selectDecision(nodeId, reason = "") {
  const { sessionId } = getState();
  if (!sessionId) throw new Error("No active session.");
  const res = await api.agent.selectDecisionNode(sessionId, nodeId, reason);
  await refreshDecisionGraph();
  await refreshExplorer();
  return res;
}

// Move / rotate / scale the selected (or first) placed building via the backend
// geometry runtime, then refresh the explorer so the viewer re-renders. dx/dy in
// meters, rotation in degrees, scale is a multiplier. Returns the backend result
// ({rejected, reason, suggestion, fits_within_site, boundary}).
export async function transformSelectedBuilding({ dx = 0, dy = 0, rotation = 0, scale = 1 } = {}) {
  const s = getState();
  if (!s.sessionId) throw new Error("No active session.");
  const buildings = s.buildings || [];
  const buildingId =
    s.selectedBuildingId ||
    (buildings[0] && (buildings[0].building_id || buildings[0].geometry_id));
  if (!buildingId) {
    pushError("No building to transform yet — generate one first.");
    return null;
  }
  setLoading("transform", true);
  try {
    const res = await api.agent.transformBuilding(s.sessionId, buildingId, {
      translate_by_xy: [dx, dy],
      rotation_degrees: rotation,
      scale,
      part_id: s.selectedPartId || "building",
    });
    // On accept, pull the updated geometry and FORCE the viewer to re-render the
    // moved/rotated building so the change is visible (not just a chat message).
    if (res && !res.rejected) {
      await refreshExplorer();
      await forceViewerRerender({ flash: true });  // BUG 2: flash what changed
    }
    return res;
  } catch (err) {
    pushError(`Transform failed: ${err.message}`);
    return null;
  } finally {
    setLoading("transform", false);
  }
}

// Architectural-feedback manipulation — the AI layer above move/rotate/scale.
// Sends natural-language design intent ("I want more daylight") to the backend
// reasoning route, which translates it into manipulation actions and executes
// them through the SAME geometry engine as transformSelectedBuilding. On success
// it pulls the updated geometry and re-renders, exactly like a manual transform.
export async function applyArchitecturalFeedback(feedback) {
  const s = getState();
  if (!s.sessionId) throw new Error("No active session.");
  const buildings = s.buildings || [];
  const buildingId =
    s.selectedBuildingId ||
    (buildings[0] && (buildings[0].building_id || buildings[0].geometry_id));
  if (!buildingId) {
    pushError("No building to manipulate yet — generate one first.");
    return null;
  }
  // Pass the SELECTED part so the manipulation targets only that geometry (the
  // central mass / a specific wing / tower), not a default element. Defaults to
  // the whole building when nothing is selected.
  const partId = s.selectedPartId || "building";
  const partName = s.selectedPartLabel || "the whole building";
  // Debug trace (spec #10): what we are about to manipulate.
  // eslint-disable-next-line no-console
  console.log("[manip] target:", { selected_part_id: partId, selected_part_name: partName, command: feedback });

  setLoading("feedback", true);
  try {
    const res = await api.agent.buildingFeedback(s.sessionId, buildingId, feedback, true, partId, partName);
    // Debug trace (spec #10): which part the backend actually modified.
    // eslint-disable-next-line no-console
    console.log("[manip] result:", { modified_part: res?.modified_part, applied: res?.applied, target_match: res?.target_match });
    if (res?.target_match === false) {
      // eslint-disable-next-line no-console
      console.warn(`[manip] TARGET MISMATCH — selected '${partId}' but modified '${res?.modified_part}'`);
    }
    // Re-render whenever the geometry ACTUALLY changed. The backend's success field is
    // `geometry_changed` — relying only on `applied` skipped the redraw for move/place
    // ops (where applied was false/undefined), so the building moved in data but the
    // viewport kept showing the old position ("Updated" with no visible movement).
    if (res && (res.geometry_changed || res.applied)) {
      await refreshExplorer();
      await forceViewerRerender({ flash: true });  // redraw + flash what changed
    }
    return res;
  } catch (err) {
    pushError(`Feedback manipulation failed: ${err.message}`);
    return null;
  } finally {
    setLoading("feedback", false);
  }
}

// Force the 3D viewer to redraw the current building geometry from the store,
// switching to the viewer view first. Used after a transform so the building
// visibly moves/rotates rather than only showing a success message.
export async function forceViewerRerender({ flash = false } = {}) {
  setState({ centerView: "viewer" });
  try {
    const viewer = await import("./views/viewerView.js");
    const s = getState();
    // After a manipulation the building lives in s.buildings (its boundary was
    // updated server-side). Draw from buildings so the new geometry shows even if
    // stale option footprints are still in the store.
    viewer.renderBuildings(s);
    // BUG 2: briefly flash/glow the changed geometry so the user immediately sees
    // what updated (2.5s). Only on a real successful manipulation.
    if (flash && typeof viewer.flashBuilding === "function") viewer.flashBuilding();
  } catch (err) {
    /* viewer mounts later — activate() will pick up state */
  }
}

// Run the REAL backend optimization (view_optimizer NSGA-II) on the selected /
// first building. Stores the ranked options in the viewer's option model so the
// Optimization panel + viewer + comparison all read real backend metrics.
export async function optimizeBuilding(opts = {}) {
  const s = getState();
  if (!s.sessionId) throw new Error("No active session.");
  const buildings = s.buildings || [];
  const buildingId =
    s.selectedBuildingId ||
    (buildings[0] && (buildings[0].building_id || buildings[0].geometry_id));
  if (!buildingId) {
    pushError("Generate a building before optimizing.");
    return null;
  }
  setLoading("optimize", true);
  try {
    const res = await api.agent.optimizeSession(s.sessionId, { building_id: buildingId, ...opts });
    const options = (res.options || []).map((o, i) => optionToViewer(o, i, res.site_area_sqm));
    setState({
      options,
      comparisonOptions: options,
      optimizationResult: res,
      visibleOptionIds: new Set(options.map((o) => o.option_id)),
      selectedOptionId: options[0]?.option_id || null,
    });
    // Re-render the viewer with the optimized footprints. Use renderScene directly
    // (not activate, which skips when meshes already exist) so the optimized options +
    // their score cards always draw over the just-cleared placed building.
    try {
      const viewer = await import("./views/viewerView.js");
      viewer.renderScene(getState().site, options);
    } catch {
      /* viewer mounts later */
    }
    return res;
  } catch (err) {
    pushError(`Optimization failed: ${err.message}`);
    return null;
  } finally {
    setLoading("optimize", false);
  }
}

// Map one backend optimization option into the flat viewer/compare option model.
function optionToViewer(o, i, siteArea) {
  return {
    option_id: o.option_id || `opt_${i + 1}`,
    building_id: o.option_id || `opt_${i + 1}`,
    shape_type: "optimized",
    footprint: (o.boundary || []).map((p) => [Number(p[0]), Number(p[1])]),
    boundary: (o.boundary || []).map((p) => [Number(p[0]), Number(p[1])]),
    // Carry courtyard/massing voids so the preview extrudes the real opening
    // (the Pareto selector's courtyard massing variants have holes).
    holes: (o.holes || []).map((h) => (h || []).map((p) => [Number(p[0]), Number(p[1])])),
    // Carry the MANIPULATED plate stack (twist/taper sculpting + per-wing added floors)
    // so the optimized preview extrudes the real per-floor geometry instead of a flat
    // block — this is what made the "futuristic appearance" + added floors vanish after
    // optimization. drawOption() extrudes each plate at its own Z when present.
    floor_plates: o.floor_plates || [],
    massing: o.massing,
    height: o.height_m || 12,
    height_m: o.height_m,
    floors: o.floors || 0,
    rotation_degrees: o.rotation_degrees || 0,
    score: o.score ?? 0,
    rank: o.rank ?? i + 1,
    status: o.fits_within_site === false ? "invalid" : "candidate",
    reasoning: o.reasoning || "",
    objective_breakdown: o.objective_breakdown || {},
    // CARRY THE MULTI-OBJECTIVE METRICS so the comparison table can show them (this
    // was the N/A bug — the mapper dropped objective_scores/strategy/headline).
    objective_scores: o.objective_scores || o.objective_breakdown || {},
    objective_metrics: o.objective_metrics || {},
    strategy_name: o.strategy_name,
    strategy_id: o.strategy_id,
    headline_metrics: o.headline_metrics || {},
    far: o.far,
    site_coverage: o.site_coverage,
    footprint_area: o.footprint_area,
    constraint_report: {
      passed: o.fits_within_site !== false && o.setback_ok !== false,
      metrics: {
        far: o.far,
        site_coverage: o.site_coverage,
        footprint_area: o.footprint_area,
        view_score: o.view_score,
        unblocked_view_score: o.unblocked_view_score,
        attractor_view_score: o.attractor_view_score,
        combined_score: o.combined_score,
        setback_ok: o.setback_ok,
        height_m: o.height_m,
        floors: o.floors,
      },
    },
  };
}

// Parse one SSE frame ("event: x\ndata: y") into {event, data}.
function parseSseChunk(block) {
  let event = "message";
  const dataLines = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
  }
  return { event, data: dataLines.join("\n") };
}

// Stream the agent's reply. Updates store live: assistant text, tool/decision
// traces, decision graph nodes, and the final AgentState. `onToken` is optional
// for incremental rendering by the chat panel.
export async function streamChat(message, { tags = [], onToken } = {}) {
  await ensureAgentAvailable();
  const sessionId = await ensureSession({ user_prompt: message });

  // NOTE: the user message is pushed once by the single caller (copilotClient
  // sendMessage). Pushing it here too caused duplicate prompt bubbles.
  setLoading("chat", true);
  setState({ isCopilotThinking: true });
  setStatus("Agent working…");

  // Reset per-turn traces; the decision graph itself is cumulative.
  setState({ toolTrace: [], plannerTrace: [], supervisorTrace: [] });

  let assistantText = "";
  // Streamed assistant message is appended once, then mutated in place.
  let assistantPushed = false;
  // Captured from the final `state` event so we can show a real reply + a
  // conversational follow-up even when the model streams no tokens.
  let finalResponse = "";
  let finalPlacedCount = 0;
  let finalViolations = [];

  const appendAssistant = (text) => {
    const s = getState();
    if (!assistantPushed) {
      pushMessage("assistant", text);
      assistantPushed = true;
    } else {
      const msgs = s.messages.slice();
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant") {
          msgs[i] = { ...msgs[i], text };
          break;
        }
      }
      setState({ messages: msgs });
    }
  };

  const recordDecision = (node) => {
    if (!node || !node.node_id) return;
    const g = getState().decisionGraph || { nodes: [], edges: [], head: null };
    if (g.nodes.some((n) => n.node_id === node.node_id)) return;
    const nodes = [...g.nodes, node];
    const edges = node.parent_id
      ? [...g.edges, { id: `${node.parent_id}-${node.node_id}`, source: node.parent_id, target: node.node_id }]
      : g.edges;
    setState({
      decisionGraph: {
        nodes,
        edges,
        head: node.is_selected ? node.node_id : g.head,
      },
    });
    // Decision-node types double as the planner/supervisor narrative.
    if (node.type === "intent") {
      setState({ supervisorTrace: [...getState().supervisorTrace, node.label] });
    } else if (node.type === "branch") {
      setState({ plannerTrace: [...getState().plannerTrace, node.label] });
    }
  };

  try {
    const res = await fetch(api.agent.chatUrl(sessionId), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ message, tags }),
    });
    if (!res.ok || !res.body) {
      throw new Error(`Chat stream failed (${res.status})`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    // SSE frames are separated by a blank line. Buffer across reads.
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        if (!block.trim()) continue;
        const { event, data } = parseSseChunk(block);

        if (event === "token") {
          assistantText += data;
          appendAssistant(assistantText);
          if (onToken) onToken(data, assistantText);
        } else if (event === "tool") {
          let t = {};
          try { t = JSON.parse(data); } catch { t = { name: data }; }
          setState({
            toolTrace: [...getState().toolTrace, t.name || "tool"],
            plannerTrace: [...getState().plannerTrace, `Tool: ${t.name}`],
          });
        } else if (event === "decision") {
          let node = null;
          try { node = JSON.parse(data); } catch { node = null; }
          recordDecision(node);
        } else if (event === "state") {
          let agentState = null;
          try { agentState = JSON.parse(data); } catch { agentState = null; }
          if (agentState) {
            setState({ agentState });
            // Capture the agent's design report so we can show it as the reply
            // when the model streamed no tokens (e.g. thinking models).
            if (agentState.final_response) finalResponse = agentState.final_response;
            if (Array.isArray(agentState.placed_buildings)) {
              finalPlacedCount = agentState.placed_buildings.length;
            }
            if (Array.isArray(agentState.violations)) finalViolations = agentState.violations;
          }
        } else if (event === "error") {
          pushError(data);
          appendAssistant((assistantText ? assistantText + "\n\n" : "") + `⚠️ ${data}`);
        } else if (event === "done") {
          // handled by stream end below
        }
      }
    }

    // If the model streamed no tokens, fall back to the agent's design report
    // from the final state instead of a bare "Done." — that report is the real
    // reply for thinking models that don't emit token streams.
    if (!assistantText && finalResponse) {
      appendAssistant(finalResponse);
    } else if (!assistantPushed && !assistantText) {
      // Last resort: the model emitted nothing. Don't repeat a robotic template —
      // tell the user they can ask what happened (the QA layer answers from state).
      appendAssistant("Done. Ask me what changed, or what to do next.");
    }

    // Pull authoritative graph + explorer once the turn settles.
    await refreshDecisionGraph();
    await refreshExplorer();

    // When a building was placed, let the workflow controller advance to the
    // SHAPE_EDIT stage (it emits the Move/Rotate/Scale/Optimize guidance), so the
    // Copilot drives the next step instead of ending the chat.
    const placed = finalPlacedCount || (getState().buildings || []).length;
    if (placed > 0) {
      if (finalViolations.length) {
        pushMessage(
          "assistant",
          `⚠️ ${finalViolations.length} constraint issue(s) flagged — I can adjust the design to resolve them.`
        );
      }
      const { enterStage } = await import("./core/workflow.js");
      const { STAGES } = await import("./core/stages.js");
      enterStage(STAGES.SHAPE_EDIT);
    }
    setStatus("Ready · Agent");
  } catch (err) {
    pushError(err.message || "Agent chat failed.");
    if (!assistantPushed) pushMessage("assistant", `⚠️ ${err.message || "Agent chat failed."}`);
    setStatus("Error");
  } finally {
    setLoading("chat", false);
    setState({ isCopilotThinking: false });
  }
}
