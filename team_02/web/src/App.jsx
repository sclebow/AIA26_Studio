import { useEffect, useRef, useState, useCallback } from "react";
import * as api from "./api/client.js";
import Overlay from "./components/Overlay.jsx";
import QuizScreen from "./screens/QuizScreen.jsx";
import LayoutModeScreen from "./screens/LayoutModeScreen.jsx";
import InspireScreen from "./screens/InspireScreen.jsx";
import PersonaScreen from "./screens/PersonaScreen.jsx";
import ProfileChatScreen from "./screens/ProfileChatScreen.jsx";
import { SelectionProvider } from "./lib/selection.jsx";

let _mid = 0;
const nextId = () => ++_mid;

const ACTION_LABELS = {
  analyze:         "comfort scored",
  detect:          "conflicts detected",
  full:            "full analysis",
  change_material: "material changed",
  modify_glazing:  "glazing modified",
  add_furniture:   "furniture added",
  topologic:       "topology mapped",
  biophilic:       "biophilic audit",
  compare:         "personas compared",
  follow_up:       "follow-up",
  overview:        "room overview",
  chitchat:        "chat",
};

function avgScore(scores_json) {
  try {
    const rooms = JSON.parse(scores_json).rooms || [];
    if (!rooms.length) return null;
    return rooms.reduce((a, r) => a + (r.overallScore || 0), 0) / rooms.length;
  } catch { return null; }
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
  const [thinking, setThinking]   = useState(false);

  // Quiz
  const [quizMessages, setQuizMessages] = useState([]);
  const [quizStep, setQuizStep]         = useState(0);

  // Layout mode: flat chat messages + structured turn history
  const [chatMessages, setChatMessages] = useState([]);
  const [turns, setTurns]               = useState([]);

  // Inspire / persona
  const [inspireMessage, setInspireMessage]   = useState("");
  const [personaMessage, setPersonaMessage]   = useState("");
  const [moodboardUrls, setMoodboardUrls]     = useState([]);

  const started = useRef(false);

  const routeResponse = useCallback((data) => {
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
      setScreen("chat");

      // Always push to flat chat thread
      setChatMessages((m) => [...m, { id: nextId(), role: "s", text: data.message, data }]);

      // Push to structured turn history when this turn has analysis data
      if (data.scores_json || data.graph_data || data.biophilic_data || data.layout_diff) {
        setTurns((prev) => [...prev, {
          id:             nextId(),
          action:         data.action || "",
          label:          ACTION_LABELS[data.action] || data.action || "turn",
          scores_json:    data.scores_json    || "",
          conflicts_json: data.conflicts_json || "",
          suggestions_json: data.suggestions_json || "",
          score_interpretation: data.score_interpretation || "",
          conflict_reasoning:   data.conflict_reasoning   || "",
          suggestion_critique:  data.suggestion_critique  || "",
          layout_diff:    data.layout_diff    || {},
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
    setChatMessages((m) => [...m, { id: nextId(), role: "u", text }]);
    setThinking(true);
    try {
      const data = await api.sendMessage(text);
      routeResponse(data);
    } catch (err) {
      setThinking(false);
      setChatMessages((m) => [...m, { id: nextId(), role: "s", text: "Something went wrong — try again." }]);
    }
  }, [routeResponse]);

  const confirmPersona = useCallback(() => setScreen("chat"), []);

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
          onConfirm={confirmPersona} onTweak={() => setScreen("profile-chat")}
        />
      )}
      {screen === "profile-chat" && (
        <ProfileChatScreen persona={persona} onConfirm={confirmPersona} />
      )}
      {screen === "chat" && (
        <SelectionProvider>
          <LayoutModeScreen
            messages={chatMessages}
            turns={turns}
            thinking={thinking}
            persona={persona}
            layoutId={layoutId}
            onSend={sendChat}
          />
        </SelectionProvider>
      )}
    </>
  );
}
