import { useState } from "react";
import { useBlockchain } from "../context/BlockchainContext";
import ReportHashVerifier from "./ReportHashVerifier";
import Status from "./Status";

/**
 * VerificationForm — checks a session id + Merkle root against verifyMerkleRoot(),
 * then offers the report-hash file check. Pass `sessionId` to lock it to one session.
 */
export default function VerificationForm({ sessionId: fixedId } = {}) {
  const { service } = useBlockchain();
  const [sessionId, setSessionId] = useState(fixedId || "");
  const [merkleRoot, setMerkleRoot] = useState("");
  const [result, setResult] = useState(null);
  const [verifying, setVerifying] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setVerifying(true);
    setResult(null);
    try {
      const ok = await service.verifyMerkleRoot(sessionId.trim(), merkleRoot.trim());
      setResult({
        ok,
        message: ok
          ? "The Merkle root matches the on-chain record."
          : "The Merkle root does not match the on-chain record, or the session was not found.",
      });
    } catch (err) {
      setResult({ ok: false, message: "Verification error: " + (err.message || String(err)) });
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="card divide-y divide-slate-200">
      <section className="p-6">
        <h2 className="text-xl font-semibold">Check a Merkle root</h2>
        <p className="mt-1 text-sm text-slate-600">Enter the session id and Merkle root to compare them with the blockchain.</p>
        <form onSubmit={handleSubmit} className="mt-5 grid gap-4 md:grid-cols-2">
          <div>
            <label htmlFor="vf-session" className="label">Session id (UUID)</label>
            <input
              id="vf-session"
              type="text"
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              placeholder="550e8400-e29b-41d4-a716-446655440000"
              className="input font-mono"
              disabled={verifying || Boolean(fixedId)}
              required
            />
          </div>
          <div>
            <label htmlFor="vf-root" className="label">Merkle root (hex)</label>
            <input
              id="vf-root"
              type="text"
              value={merkleRoot}
              onChange={(e) => setMerkleRoot(e.target.value)}
              placeholder="0x followed by 64 hex characters"
              className="input font-mono"
              disabled={verifying}
              required
            />
            <p className="mt-1.5 text-xs text-slate-500">The 0x prefix is optional.</p>
          </div>
          <div className="md:col-span-2">
            <button type="submit" disabled={verifying} className="btn-primary">
              {verifying ? "Checking…" : "Check Merkle root"}
            </button>
          </div>
        </form>
        {result && (
          <div role="status" className={`mt-5 flex items-start gap-3 rounded-lg p-4 text-sm ${result.ok ? "bg-emerald-50 text-emerald-900" : "bg-rose-50 text-rose-900"}`}>
            <Status state={result.ok} />
            <span className="pt-0.5">{result.message}</span>
          </div>
        )}
        <details className="note mt-5">
          <summary className="cursor-pointer font-medium text-slate-700">How this check works</summary>
          <p className="mt-2">
            The dashboard calls <code>verifyMerkleRoot(sessionId, merkleRoot)</code> on the AuditLedger contract. Only hashes are
            compared, so no raw activity data is exposed. In demo mode the result is simulated.
          </p>
        </details>
      </section>
      <section className="p-6">
        <ReportHashVerifier sessionId={fixedId} />
      </section>
    </div>
  );
}
