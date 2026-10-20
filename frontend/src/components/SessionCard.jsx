import { Link } from "react-router-dom";
import Fingerprint from "./Fingerprint";
import Status from "./Status";
import { short, when } from "../utils/format";

/** One row in the session list; the whole row links to the details page. */
export default function SessionCard({
  id, timestamp, merkleRoot, score, grade, verified, txHash,
  classification, confidence, modelVersion, featureVersion,
  synthetic = false, demo = false,
}) {
  const tone =
    score == null ? "text-slate-500" : score >= 65 ? "text-emerald-700" : score >= 35 ? "text-amber-700" : "text-rose-700";

  return (
    <Link to={`/sessions/${encodeURIComponent(id)}`} className="block px-5 py-4 transition hover:bg-slate-50">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <Fingerprint value={id} />
          <div className="min-w-0">
            <p className="flex items-center gap-2">
              <span className="truncate font-mono text-sm font-medium">{demo ? id : short(id, 8, 6)}</span>
              {(demo || synthetic) && (
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800">Synthetic</span>
              )}
            </p>
            <p className="mt-0.5 text-xs text-slate-500">{when(timestamp)}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
          <div>
            <p className="text-xs text-slate-500">Effort score</p>
            <p className={`font-semibold ${tone}`}>{score == null ? "—" : score}{grade ? ` (${grade})` : ""}</p>
          </div>
          <div>
            <p className="text-xs text-slate-500">ML outcome</p>
            <p className="font-medium text-slate-700">
              {classification || "—"}{confidence != null ? ` (${Math.round(confidence * 100)}%)` : ""}
            </p>
          </div>
          <Status state={verified} />
        </div>
      </div>
      <p className="mt-3 flex flex-wrap gap-x-5 gap-y-1 font-mono text-xs text-slate-500">
        <span>Merkle {short(merkleRoot)}</span>
        <span>Model {modelVersion || "—"} / Features {featureVersion || "—"}</span>
        {txHash && <span>Tx {short(txHash)}</span>}
      </p>
    </Link>
  );
}
