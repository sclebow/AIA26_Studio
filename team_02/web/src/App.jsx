import { useEffect, useRef, useState, useCallback } from "react";
import * as api from "./api/client.js";
import Overlay from "./components/Overlay.jsx";
import QuizScreen from "./screens/QuizScreen.jsx";
import LayoutModeScreen from "./screens/LayoutModeScreen.jsx";
import InspireScreen from "./screens/InspireScreen.jsx";
import PersonaScreen from "./screens/PersonaScreen.jsx";
import ReportScreen from "./report/ReportScreen.jsx";
import { SelectionProvider } from "./lib/selection.jsx";
import { layoutScore } from "./lib/turn.js";

let _mid = 0;
const nextId = () => ++_mid;

const ACTION_LABELS = {
  analyze:         "comfort scored",
  detect:          "conflicts detected",
  full:            "full analysis",
  edit:            "change applied",
  topologic:       "topology mapped",
  biophilic:       "biophilic audit",
  compare:         "personas compared",
  follow_up:       "follow-up",
  overview:        "room overview",
  chitchat:        "chat",
};

function avgScore(scores_json) {
  try { return layoutScore(JSON.parse(scores_json).rooms || []); }
  catch { return null; }
}

function conflictCount(conflicts_json) {
  try { return (JSON.parse(conflicts_json).flaggedRooms || []).length; }
  catch { return 0; }
}

export default function App() {
  const [screen, setScreen]       = useState("quiz");
  const [overlay, setOverlay]     = useState("starting sensi...");
  const [persona, setPersona]     = useState(null);
  const [layoutId, setLayoutId]   = useState(null);
  const [layoutVersion, setLayoutVersion] = useState(0); // bumped after edits to force a plan re-fetch
  const [thinking, setThinking]   = useState(false);

  // Quiz
  const [quizMessages, setQuizMessages] = useState([]);
  const [quizStep, setQuizStep]         = useState(0);

  // Layout mode: flat chat messages + structured turn history
  const [chatMessages, setChatMessages] = useState([]);
  const [turns, setTurns]               = useState([]);

  // Checkpoints (Task 3): committed milestones + uncommitted working-draft status
  const [checkpoints, setCheckpoints]         = useState([]);
  const [hasUncommitted, setHasUncommitted]   = useState(false);
  const [uncommittedDelta, setUncommittedDelta] = useState({});
  const [liveHead, setLiveHead]               = useState(null); // uncommitted draft as a graph point
  const [viewedTurn, setViewedTurn]           = useState(null); // a checkpoint being reviewed

  // Inspire / persona
  const [inspireMessage, setInspireMessage]   = useState("");
  const [personaMessage, setPersonaMessage]   = useState("");
  const [moodboardUrls, setMoodboardUrls]     = useState([]);

  const started = useRef(false);
  const [streaming, setStreaming] = useState(false); // a chat turn is streaming
  const abortRef = useRef(null);                     // AbortController for the live turn

  // existingId: when a streaming turn already created a live assistant bubble, finalize
  // THAT message instead of pushing a duplicate. Non-streaming callers omit it.
  const routeResponse = useCallback((data, existingId = null) => {
    setThinking(false);
    setOverlay(null);

    if (data.screen === "quiz") {
      setScreen("quiz");
      setQuizMessages((m) => [...m, { id: nextId(), role: "s", text: data.message }]);
      setQuizStep(data.quiz_step || 0);

    } else if (data.screen === "inspire") {
      setScreen("inspire");
      setInspireMessage(data.message || "");

    } else if (data.screen === "chat") {
      const newLayoutId = data.layout_id || null;
      setLayoutId(newLayoutId);
      // An edit tool mutated the layout (e.g. added furniture) — force the plan
      // canvas to re-fetch so the change actually renders.
      if (data.layout_updated) setLayoutVersion((v) => v + 1);
      setScreen("chat");

      // Push to the flat chat thread — or finalize the live streaming bubble in place.
      if (existingId != null) {
        setChatMessages((m) => m.map((msg) => msg.id === existingId
          ? { ...msg, text: data.message, data, streaming: false, tokensStarted: true }
          : msg));
      } else {
        setChatMessages((m) => [...m, { id: nextId(), role: "s", text: data.message, data }]);
      }

      // Checkpoint state rides along on every turn
      if (data.checkpoints) setCheckpoints(data.checkpoints);
      setHasUncommitted(!!data.has_uncommitted);
      setUncommittedDelta(data.uncommitted_delta || {});
      setLiveHead(data.live_head ?? null);

      // Normalize edit diffs to an array once, so every downstream consumer can
      // trust turn.layout_diffs is always an array (single-edit → 1-element array).
      const diffs = data.layout_diffs?.length
        ? data.layout_diffs
        : (data.layout_diff && Object.keys(data.layout_diff).length ? [data.layout_diff] : []);
      const isMultiEdit = data.action === "edit" && diffs.length > 1;

      // Push to structured turn history when this turn has analysis data
      if (data.scores_json || data.graph_data || data.biophilic_data || diffs.length || data.preview_scores_json) {
        setTurns((prev) => [...prev, {
          id:             nextId(),
          action:         data.action || "",
          label:          isMultiEdit ? `${diffs.length} changes`
                            : (ACTION_LABELS[data.action] || data.action || "turn"),
          scores_json:    data.scores_json    || "",
          conflicts_json: data.conflicts_json || "",
          suggestions_json: data.suggestions_json || "",
          score_interpretation: data.score_interpretation || "",
          conflict_reasoning:   data.conflict_reasoning   || "",
          suggestion_critique:  data.suggestion_critique  || "",
          layout_diff:    data.layout_diff    || {},
          layout_diffs:   diffs,
          preview_scores_json: data.preview_scores_json || "",
          preview_diff:   data.preview_diff   || {},
          preview_summary: data.preview_summary || "",
          graph_data:     data.graph_data     || {},
          biophilic_data: data.biophilic_data || {},
          persona_comparison_data: data.persona_comparison_data || {},
          avgScore:       avgScore(data.scores_json),
          conflictCount:  conflictCount(data.conflicts_json),
          timestamp:      Date.now(),
        }]);
      }
    }
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    api.init()
      .then((data) => {
        setOverlay(null);
        if (data.screen === "chat") {
          if (data.persona) setPersona(data.persona);
          setLayoutId(data.layout_id || null);
          setScreen("chat");
          setChatMessages([{ id: nextId(), role: "s", text: data.message }]);
        } else {
          setScreen("quiz");
          setQuizMessages([{ id: nextId(), role: "s", text: data.message }]);
          setQuizStep(data.quiz_step || 0);
        }
      })
      .catch((err) => {
        setOverlay(null);
        setQuizMessages([{ id: nextId(), role: "s", text: "Could not reach Sensi: " + err.message }]);
        setScreen("quiz");
      });
  }, []);

  const submitQuiz = useCallback(async (text) => {
    setQuizMessages((m) => [...m, { id: nextId(), role: "u", text }]);
    setThinking(true);
    try {
      const data = await api.sendMessage(text);
      routeResponse(data);
    } catch (err) {
      setThinking(false);
      setQuizMessages((m) => [...m, { id: nextId(), role: "s", text: "Something went wrong — try again." }]);
    }
  }, [routeResponse]);

  const sendChat = useCallback(async (text) => {
    setViewedTurn(null); // a new message returns the panel to the live working draft
    const msgId = nextId();
    setChatMessages((m) => [...m,
      { id: nextId(), role: "u", text },
      { id: msgId, role: "s", text: "Thinking", streaming: true, tokensStarted: false },
    ]);

    const setMsg = (fn) => setChatMessages((m) => m.map((x) => (x.id === msgId ? fn(x) : x)));
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming(true);

    try {
      await api.sendMessageStream(text, {
        // Progress labels show in the bubble ONLY until the answer starts streaming.
        onProgress: (p) => setMsg((x) => (x.tokensStarted ? x : { ...x, text: p.message })),
        // Fresh answer (also fires on the evaluator REVISE re-run) — reset the buffer.
        onMessageStart: () => setMsg((x) => ({ ...x, text: "", tokensStarted: true })),
        onToken: (t) => setMsg((x) => ({ ...x, text: x.text + t, tokensStarted: true })),
        // result carries the full payload — finalize panel/turns/checkpoints exactly
        // as the non-streaming path, updating this bubble in place.
        onResult: (data) => routeResponse(data, msgId),
        onError: (msg) => setMsg((x) => ({
          ...x, streaming: false, tokensStarted: true,
          text: "Something went wrong — " + (msg || "try again") +
                ". Your message is above; rephrase or resend.",
        })),
      }, ctrl.signal);
    } catch (err) {
      const aborted = ctrl.signal.aborted;
      setMsg((x) => ({
        ...x, streaming: false, tokensStarted: true,
        text: aborted ? (x.text && x.text !== "Thinking" ? x.text + "\n\n(stopped)" : "Stopped.")
                      : "Something went wrong — try again.",
      }));
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [routeResponse]);

  const stopChat = useCallback(() => { abortRef.current?.abort(); }, []);

  const commitCheckpoint = useCallback(async (label) => {
    try {
      const d = await api.commit(label);
      if (d.ok) {
        if (d.checkpoints) setCheckpoints(d.checkpoints);
        setHasUncommitted(!!d.has_uncommitted);
        setUncommittedDelta({});
        setLiveHead(d.live_head ?? null);
      }
    } catch { /* leave uncommitted state as-is on failure */ }
  }, []);

  const viewCheckpoint = useCallback(async (id) => {
    try {
      const d = await api.viewCheckpoint(id);
      if (!d.ok) return;
      setViewedTurn({
        id: "cp" + d.id, checkpointId: d.id, action: "checkpoint", label: d.label,
        scores_json: d.scores_json || "", conflicts_json: d.conflicts_json || "",
        suggestions_json: d.suggestions_json || "",
      });
    } catch { /* ignore */ }
  }, []);
  const clearViewedCheckpoint = useCallback(() => setViewedTurn(null), []);

  const restoreCheckpoint = useCallback(async (id) => {
    try {
      const d = await api.restore(id);
      if (!d.ok) return;
      if (d.checkpoints) setCheckpoints(d.checkpoints);
      setHasUncommitted(!!d.has_uncommitted);
      setUncommittedDelta({});
      setLiveHead(d.live_head ?? null);
      setViewedTurn(null);
      setLayoutVersion((v) => v + 1); // working draft changed → re-fetch the canvas
      setChatMessages((m) => [...m, { id: nextId(), role: "s",
        text: `Restored to "${d.restored_label}" — the canvas now shows that checkpoint.` }]);
      if (d.scores_json) {
        setTurns((prev) => [...prev, {
          id: nextId(), action: "restore", label: `restored: ${d.restored_label}`,
          scores_json: d.scores_json || "", conflicts_json: d.conflicts_json || "",
          suggestions_json: d.suggestions_json || "", layout_diff: {}, layout_diffs: [],
          avgScore: avgScore(d.scores_json), conflictCount: conflictCount(d.conflicts_json),
          timestamp: Date.now(),
        }]);
      }
    } catch { /* ignore */ }
  }, []);

  const confirmPersona = useCallback(() => setScreen("chat"), []);
  const goReport = useCallback(() => setScreen("report"), []);

  // Refine the persona from a free-text statement ("I got a dog, noise bothers me more").
  // The backend patches + persists it; we update local state so the drawer card and all
  // subsequent scoring/answers use the new persona. Returns the confirmation line.
  const refinePersona = useCallback(async (text) => {
    const data = await api.refinePersona(text);
    if (data.persona) setPersona(data.persona);
    return data.message || "Updated your comfort profile.";
  }, []);

  // Start onboarding over: clear the persona + working state and return to the quiz.
  const redoOnboarding = useCallback(async () => {
    const data = await api.resetPersona();
    setPersona(null);
    setChatMessages([]);
    setTurns([]);
    setCheckpoints([]);
    setHasUncommitted(false);
    setUncommittedDelta({});
    setLiveHead(null);
    setQuizMessages([{ id: nextId(), role: "s", text: data.message }]);
    setQuizStep(data.quiz_step || 0);
    setScreen("quiz");
  }, []);

  return (
    <>
      <Overlay message={overlay} />

      {screen === "quiz" && (
        <QuizScreen messages={quizMessages} step={quizStep} thinking={thinking} onSubmit={submitQuiz} />
      )}
      {screen === "inspire" && (
        <InspireScreen
          question={inspireMessage}
          setOverlay={setOverlay}
          onPersonaReady={(data) => {
            setPersona(data.persona || null);
            setPersonaMessage(data.message || "");
            setMoodboardUrls(data.moodboard_urls || []);
            setScreen("persona");
          }}
        />
      )}
      {screen === "persona" && (
        <PersonaScreen
          persona={persona} message={personaMessage} moodboardUrls={moodboardUrls}
          onConfirm={confirmPersona}
        />
      )}
      {screen === "chat" && (
        <SelectionProvider>
          <LayoutModeScreen
            messages={chatMessages}
            turns={turns}
            thinking={thinking}
            persona={persona}
            moodboardUrls={moodboardUrls}
            onRefinePersona={refinePersona}
            onRedoOnboarding={redoOnboarding}
            layoutId={layoutId}
            layoutVersion={layoutVersion}
            onSend={sendChat}
            streaming={streaming}
            onStop={stopChat}
            onReport={goReport}
            checkpoints={checkpoints}
            hasUncommitted={hasUncommitted}
            uncommittedDelta={uncommittedDelta}
            liveHead={liveHead}
            onCommit={commitCheckpoint}
            onRestore={restoreCheckpoint}
            viewedTurn={viewedTurn}
            onViewCheckpoint={viewCheckpoint}
            onClearView={clearViewedCheckpoint}
          />
        </SelectionProvider>
      )}
      {screen === "report" && (
        <SelectionProvider>
          <ReportScreen
            turn={turns.length ? turns[turns.length - 1] : null}
            persona={persona}
            layoutId={layoutId}
            onBack={() => setScreen("chat")}
          />
        </SelectionProvider>
      )}
    </>
  );
}
