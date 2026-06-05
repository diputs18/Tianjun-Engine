import { createContext, useContext, useEffect, useState } from "react";
import { useChatStream } from "../../hooks/useChatStream.js";
import { useControlPlaneContext } from "../../layout/ControlPlaneProvider.jsx";

const SchedulingSessionContext = createContext(null);
const SESSION_STORAGE_KEY = "tianjun:scheduling-session:v1";
const DRAFT_STORAGE_KEY = `${SESSION_STORAGE_KEY}:draft`;

export function SchedulingSessionProvider({ children }) {
  const { refresh } = useControlPlaneContext();
  const chat = useChatStream({
    onCommitted: refresh,
    storageKey: SESSION_STORAGE_KEY,
  });
  const [draft, setDraft] = useState(() => {
    if (typeof window === "undefined") return "";
    return window.sessionStorage.getItem(DRAFT_STORAGE_KEY) ?? "";
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!draft) {
      window.sessionStorage.removeItem(DRAFT_STORAGE_KEY);
      return;
    }
    window.sessionStorage.setItem(DRAFT_STORAGE_KEY, draft);
  }, [draft]);

  return (
    <SchedulingSessionContext.Provider value={{ chat, draft, setDraft }}>
      {children}
    </SchedulingSessionContext.Provider>
  );
}

export function useSchedulingSession() {
  const context = useContext(SchedulingSessionContext);
  if (!context) {
    throw new Error("useSchedulingSession must be used inside SchedulingSessionProvider");
  }
  return context;
}
