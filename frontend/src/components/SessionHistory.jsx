import { useMemo, useState } from "react";
import { useBlockchain } from "../context/BlockchainContext";
import { useSessions } from "../hooks/useSessions";
import SessionCard from "./SessionCard";
import EmptyState from "./EmptyState";
import Gate from "./Gate";

/** Lists every recorded session and adds new ones live as they are anchored. */
export default function SessionHistory() {
  const { demo } = useBlockchain();
  const { sessions, loading, error, reload, status } = useSessions({ live: true });
  const [query, setQuery] = useState("");

  const filtered = useMemo(
    () => sessions.filter((s) => s.id.toLowerCase().includes(query.toLowerCase())),
    [sessions, query]
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Session history</h1>
        <p className="mt-2 text-slate-600">Every session recorded on the ledger, newest first.</p>
      </header>
      <Gate loading={loading} error={error} status={status} onRetry={reload}>
        {sessions.length === 0 ? (
          <EmptyState
            title={demo ? "No demo sessions yet" : "No sessions recorded"}
            description={
              demo
                ? "Submit a session from the Python pipeline to see records here."
                : "Run python log_effort.py to record a session on-chain. It will appear here."
            }
            action={<button onClick={reload} className="btn-ghost">Refresh</button>}
          />
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="search"
                aria-label="Search session id"
                placeholder="Search by session id"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="input max-w-sm"
              />
              <span className="text-sm text-slate-500">
                {filtered.length} of {sessions.length} sessions
              </span>
            </div>
            <div className="card divide-y divide-slate-200 overflow-hidden">
              {filtered.map((s) => (
                <SessionCard
                  key={s.id}
                  id={s.id}
                  timestamp={s.timestamp}
                  merkleRoot={s.merkleRoot}
                  score={s.score}
                  grade={s.grade}
                  verified={s.verified}
                  txHash={s.txHash}
                  classification={s.classification}
                  confidence={s.confidence}
                  modelVersion={s.modelVersion}
                  featureVersion={s.featureVersion}
                  synthetic={s.synthetic}
                  demo={s.demo}
                />
              ))}
              {filtered.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No session matches that id.</p>}
            </div>
          </>
        )}
      </Gate>
    </div>
  );
}
