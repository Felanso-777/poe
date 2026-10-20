import { useParams, useNavigate, Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { useBlockchain } from "../context/BlockchainContext";
import Gate from "../components/Gate";
import Fingerprint from "../components/Fingerprint";
import VerificationForm from "../components/VerificationForm";
import { when } from "../utils/format";

export default function SessionDetails() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { service, demo, status, error: connectionError } = useBlockchain();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);

  const sessionId = id ? decodeURIComponent(id) : "";

  useEffect(() => {
    if (!sessionId) {
      navigate("/history");
      return;
    }
    let cancelled = false;
    if (status !== "connected") {
      setLoading(status === "connecting");
      setError(status === "error" ? connectionError || "Blockchain connection failed" : null);
      return;
    }
    setLoading(true);
    setError(null);
    service
      .getSession(sessionId)
      .then((record) => {
        if (cancelled) return;
        setSession(record);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || String(err));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [service, sessionId, navigate, status, connectionError, tick]);

  const rows = session && [
    ["Session id (bytes32)", session.sessionId, true],
    ["Merkle root", session.merkleRoot, true],
    ["Recorded", when(session.timestamp)],
    ["Submitter", session.submitter, true],
    ["Report hash", session.reportHash || "—", true],
    ["Model / features", `${session.modelVersion} / ${session.featureVersion}`],
    ["ML classification", `${session.classification ?? "—"}${session.confidence != null ? ` (${Math.round(session.confidence * 100)}%)` : ""}`],
    ["Heuristic score", session.score == null ? "—" : session.score],
    ["Data source", demo || session.synthetic ? "Simulated (demo)" : "Live (on-chain)"],
  ];

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header>
        <Link to="/history" className="text-sm font-medium text-poe-700 hover:underline">Back to history</Link>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">Session details</h1>
        <p className="mt-2 break-all font-mono text-sm text-slate-600">{sessionId}</p>
      </header>

      <Gate loading={loading} error={error} status={status} onRetry={() => setTick((t) => t + 1)}>
        {session && (
          <>
            <section className="card p-6">
              <div className="flex items-center gap-3">
                <Fingerprint value={session.merkleRoot} cells={16} />
                <h2 className="text-lg font-semibold">On-chain record</h2>
              </div>
              <dl className="mt-4 divide-y divide-slate-100">
                {rows.map(([label, value, mono]) => (
                  <div key={label} className="grid gap-1 py-3 sm:grid-cols-[11rem_1fr] sm:gap-4">
                    <dt className="text-sm text-slate-500">{label}</dt>
                    <dd className={`min-w-0 break-all text-sm ${mono ? "font-mono" : "font-medium"}`}>{value}</dd>
                  </div>
                ))}
              </dl>
            </section>

            <section className="card p-6">
              <h2 className="text-lg font-semibold">Analysis summary</h2>
              <p className="mt-2 text-sm text-slate-600">
                The effort score and behavioural metrics come from the local Python analysis engine. Only the report hash is
                anchored on-chain.
              </p>
              <p className="note mt-4">
                Open <code>{sessionId}-report.json</code> from the Python pipeline to see the full heuristic breakdown, grade and
                confidence metrics.
              </p>
            </section>

            <VerificationForm sessionId={sessionId} />
          </>
        )}
      </Gate>
    </div>
  );
}
