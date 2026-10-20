import { useEffect, useState, useCallback } from "react";
import { useBlockchain } from "../context/BlockchainContext";

/** Loads all sessions; optionally appends new ones live from SessionRecorded events. */
export function useSessions({ live = false } = {}) {
  const { service, status, error: connectionError } = useBlockchain();
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    if (status !== "connected") {
      setLoading(status === "connecting");
      setError(status === "error" ? connectionError || "Blockchain connection failed" : null);
      return;
    }
    setLoading(true);
    setError(null);
    service
      .fetchAllSessions()
      .then((list) => {
        if (cancelled) return;
        setSessions(list);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || String(err));
        setLoading(false);
      });
    const off = live
      ? service.onSessionRecorded((ev) =>
          setSessions((prev) =>
            prev.some((s) => s.sessionId === ev.sessionId)
              ? prev
              : [{ id: ev.sessionId, ...ev, score: null, grade: null, verified: null, demo: false }, ...prev]
          )
        )
      : () => {};
    return () => {
      cancelled = true;
      off();
    };
  }, [service, status, connectionError, tick, live]);

  return { sessions, loading, error, reload, status };
}
