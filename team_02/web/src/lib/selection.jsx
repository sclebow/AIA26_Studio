import { createContext, useCallback, useContext, useMemo, useState } from "react";

/*
 * Selection bus — one shared selection state for the whole instrument.
 *
 * Principle 3 (shared selection bus): a single source of truth for "what is
 * the user pointing at" so every view — plan, signature, radar, timeline,
 * mixer, panel — cross-highlights from the same state instead of each keeping
 * its own.
 *
 *   activeSense : string | null   one of SENSES, or null for "all"
 *   activeRoom  : string | null   a roomName, or null for "none"
 *   hoverSense  : string | null   transient hover (does not pin)
 *
 * Pinning vs hover: setActiveSense pins (click); setHoverSense is transient
 * (mouseenter/leave). Views should treat (hoverSense ?? activeSense) as the
 * effective focus so a hover previews and a click sticks.
 */
const SelectionContext = createContext(null);

export function SelectionProvider({ children }) {
  const [activeSense, setActiveSense] = useState(null);
  const [activeRoom, setActiveRoom] = useState(null);
  const [hoverSense, setHoverSense] = useState(null);
  const [hoverRoom, setHoverRoom] = useState(null);

  const toggleSense = useCallback(
    (s) => setActiveSense((cur) => (cur === s ? null : s)),
    []
  );
  const clear = useCallback(() => {
    setActiveSense(null);
    setActiveRoom(null);
    setHoverSense(null);
    setHoverRoom(null);
  }, []);

  const value = useMemo(
    () => ({
      activeSense, setActiveSense, toggleSense,
      activeRoom, setActiveRoom,
      hoverSense, setHoverSense,
      hoverRoom, setHoverRoom,
      // hover previews, click pins — same rule for senses and rooms
      focusSense: hoverSense ?? activeSense,
      focusRoom: hoverRoom ?? activeRoom,
      clear,
    }),
    [activeSense, activeRoom, hoverSense, hoverRoom, toggleSense, clear]
  );

  return (
    <SelectionContext.Provider value={value}>
      {children}
    </SelectionContext.Provider>
  );
}

// Safe to call outside a provider — returns inert defaults so components can be
// dropped anywhere without crashing during incremental migration.
const INERT = {
  activeSense: null, setActiveSense: () => {}, toggleSense: () => {},
  activeRoom: null, setActiveRoom: () => {},
  hoverSense: null, setHoverSense: () => {},
  hoverRoom: null, setHoverRoom: () => {},
  focusSense: null, focusRoom: null, clear: () => {},
};

export function useSelection() {
  return useContext(SelectionContext) ?? INERT;
}
