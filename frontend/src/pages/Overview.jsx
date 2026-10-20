import { Link } from "react-router-dom";
import { useBlockchain } from "../context/BlockchainContext";
import { useSessions } from "../hooks/useSessions";
import Gate from "../components/Gate";
import ConnectionStatus from "../components/ConnectionStatus";
import Fingerprint from "../components/Fingerprint";
import Status from "../components/Status";
import { short, when } from "../utils/format";

export default function Overview() {
  const { account, demo } = useBlockchain();
  const { sessions, loading, error, reload, status } = useSessions({ live: true });
  const latest = sessions[0];
  const verified = sessions.filter((s) => s.verified === true).length;

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Your proof ledger</h1>
          <p className="mt-2 max-w-xl text-slate-600">
            Every effort session is anchored on-chain as a Merkle root. Check any of them against the AuditLedger contract.
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/history" className="btn-ghost">View history</Link>
          <Link to="/verify" className="btn-primary">Verify a session</Link>
        </div>
      </header>

      <Gate loading={loading} error={error} status={status} onRetry={reload}>
        {latest ? (
          <Link to={`/sessions/${encodeURIComponent(latest.id)}`} className="card block p-6 transition hover:border-slate-300">
            <p className="text-sm font-medium text-slate-500">Latest anchored proof</p>
            <div className="mt-4 flex flex-wrap items-center gap-5">
              <Fingerprint value={latest.merkleRoot} cells={16} big />
              <Status state={latest.verified} />
            </div>
            <p className="mt-4 break-all font-mono text-sm">{demo ? latest.id : short(latest.id, 12, 8)}</p>
            <p className="mt-1 text-sm text-slate-500">
              Merkle root {short(latest.merkleRoot, 10, 8)}, recorded {when(latest.timestamp)}
            </p>
          </Link>
        ) : (
          <p className="card p-6 text-sm text-slate-600">
            No sessions yet. Run <code>python log_effort.py</code> to anchor your first one.
          </p>
        )}

        <dl className="card grid divide-y divide-slate-200 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          <div className="p-5"><dt className="text-sm text-slate-500">Sessions recorded</dt><dd className="mt-1 font-display text-3xl font-semibold">{sessions.length}</dd></div>
          <div className="p-5"><dt className="text-sm text-slate-500">Verified</dt><dd className="mt-1 font-display text-3xl font-semibold text-emerald-700">{verified}</dd></div>
          <div className="min-w-0 p-5"><dt className="text-sm text-slate-500">Connected account</dt><dd className="mt-2 truncate font-mono text-sm" title={account || ""}>{account || "—"}</dd></div>
        </dl>

        {sessions.length > 0 && (
          <section>
            <h2 className="mb-3 text-lg font-semibold">Recent activity</h2>
            <ul className="card divide-y divide-slate-200 overflow-hidden">
              {sessions.slice(0, 5).map((s) => (
                <li key={s.id}>
                  <Link to={`/sessions/${encodeURIComponent(s.id)}`} className="flex items-center gap-4 px-5 py-3.5 transition hover:bg-slate-50">
                    <Fingerprint value={s.id} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-mono text-sm font-medium">{demo ? s.id : short(s.id, 8, 6)}</p>
                      <p className="text-xs text-slate-500">{when(s.timestamp)}</p>
                    </div>
                    <Status state={s.verified} />
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </Gate>

      <ConnectionStatus />
    </div>
  );
}
