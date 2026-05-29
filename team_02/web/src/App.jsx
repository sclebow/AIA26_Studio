import { useEffect, useRef, useState, useCallback } from "react";
import * as api from "./api/client.js";
import Overlay from "./components/Overlay.jsx";
import QuizScreen from "./screens/QuizScreen.jsx";
import ChatScreen from "./screens/ChatScreen.jsx";
import InspireScreen from "./screens/InspireScreen.jsx";
import PersonaScreen from "./screens/PersonaScreen.jsx";
import ProfileChatScreen from "./screens/ProfileChatScreen.jsx";

let _mid = 0;
const nextId = () => ++_mid;

// Central state machine + router. Replaces the imperative showScreen() / S{} /
// window.receive* model from index.html with React state.
export default function App() {
  const [screen, setScreen] = useState("quiz");
  const [overlay, setOverlay] = useState("starting sensi...");
  const [persona, setPersona] = useState(null);
  const [layoutId, setLayoutId] = useState(null);
  const [thinking, setThinking] = useState(false);

  const [quizMessages, setQuizMessages] = useState([]);
  const [quizStep, setQuizStep] = useState(0);

  const [chatMessages, setChatMessages] = useState([]);
  const [inspireMessage, setInspireMessage] = useState("");
  const [personaMessage, setPersonaMessage] = useState("");
  const [moodboardUrls, setMoodboardUrls] = useState([]);

  const started = useRef(false);

  // Routing of a single agent turn's response.
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
      setLayoutId(data.layout_id || null);
      setScreen("chat");
      setChatMessages((m) => [...m, { id: nextId(), role: "s", text: data.message, data }]);
    }
  }, []);

  // Startup: init session, route to quiz or chat.
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    api
      .init()
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

  const confirmPersona = useCallback(() => {
    setScreen("chat");
  }, []);

  return (
    <>
      <Overlay message={overlay} />

      {screen === "quiz" && (
        <QuizScreen
          messages={quizMessages}
          step={quizStep}
          thinking={thinking}
          onSubmit={submitQuiz}
        />
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
          persona={persona}
          message={personaMessage}
          moodboardUrls={moodboardUrls}
          onConfirm={confirmPersona}
          onTweak={() => setScreen("profile-chat")}
        />
      )}

      {screen === "profile-chat" && (
        <ProfileChatScreen persona={persona} onConfirm={confirmPersona} />
      )}

      {screen === "chat" && (
        <ChatScreen
          messages={chatMessages}
          thinking={thinking}
          persona={persona}
          layoutId={layoutId}
          onSend={sendChat}
        />
      )}
    </>
  );
}
