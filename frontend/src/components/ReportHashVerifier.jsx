import { useState } from "react";
import { useBlockchain } from "../context/BlockchainContext";
import Status from "./Status";

/**
 * ReportHashVerifier — lets a user upload their local -report.json file and
 * verify its SHA-256 hash against the value stored on-chain.
 *
 * Browsers cannot secretly read local files, so the user must explicitly
 * select the file via the file input. The hash is computed entirely in the
 * browser using the Web Crypto API; no file contents are sent to any server.
 */
export default function ReportHashVerifier({ sessionId } = {}) {
  const { service } = useBlockchain();
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null); // { ok: boolean, message: string }
  const [verifying, setVerifying] = useState(false);
  const [sessionIdInput, setSessionIdInput] = useState(sessionId || "");

  /**
   * Recursively strip fields that Python's _compute_hash excludes:
   *   - report_hash
   *   - generated_at
   *   - any key starting with "_" (private fields from dataclass serialisation)
   */
  const stripExcluded = (obj) => {
    if (Array.isArray(obj)) {
      return obj.map(stripExcluded);
    }
    if (obj !== null && typeof obj === "object") {
      if (
        Object.keys(obj).length === 1 &&
        typeof obj.__reportNumberToken === "string"
      ) {
        return obj;
      }
      const result = {};
      for (const [key, value] of Object.entries(obj)) {
        if (key === "report_hash" || key === "generated_at") continue;
        if (key.startsWith("_")) continue;
        result[key] = stripExcluded(value);
      }
      return result;
    }
    return obj;
  };

  // Python's json.loads/json.dumps preserves the distinction between values
  // such as 85.0 and 85. Keep number tokens while parsing so the browser does
  // not lose that distinction before canonicalisation.
  const parseJsonWithNumberTokens = (text) => {
    let index = 0;
    const whitespace = () => {
      while (/\s/.test(text[index] || "")) index += 1;
    };
    const parseString = () => {
      const start = index;
      index += 1;
      let escaped = false;
      while (index < text.length) {
        const char = text[index];
        index += 1;
        if (escaped) {
          escaped = false;
        } else if (char === "\\") {
          escaped = true;
        } else if (char === '"') {
          return JSON.parse(text.slice(start, index));
        }
      }
      throw new Error("Invalid JSON string");
    };
    const parseValue = () => {
      whitespace();
      const char = text[index];
      if (char === "{") {
        index += 1;
        const object = {};
        whitespace();
        if (text[index] === "}") {
          index += 1;
          return object;
        }
        while (true) {
          whitespace();
          const key = parseString();
          whitespace();
          if (text[index] !== ":") throw new Error("Invalid JSON object");
          index += 1;
          object[key] = parseValue();
          whitespace();
          if (text[index] === "}") {
            index += 1;
            return object;
          }
          if (text[index] !== ",") throw new Error("Invalid JSON object");
          index += 1;
        }
      }
      if (char === "[") {
        index += 1;
        const array = [];
        whitespace();
        if (text[index] === "]") {
          index += 1;
          return array;
        }
        while (true) {
          array.push(parseValue());
          whitespace();
          if (text[index] === "]") {
            index += 1;
            return array;
          }
          if (text[index] !== ",") throw new Error("Invalid JSON array");
          index += 1;
        }
      }
      if (char === '"') {
        return parseString();
      }
      if (text.startsWith("true", index)) {
        index += 4;
        return true;
      }
      if (text.startsWith("false", index)) {
        index += 5;
        return false;
      }
      if (text.startsWith("null", index)) {
        index += 4;
        return null;
      }
      const start = index;
      while (index < text.length && /[^\s,}\]]/.test(text[index])) {
        index += 1;
      }
      const token = text.slice(start, index);
      if (/^-?\d/.test(token)) {
        return { __reportNumberToken: token };
      }
      return token;
    };
    whitespace();
    const value = parseValue();
    whitespace();
    if (index !== text.length) {
      throw new Error("Invalid JSON: trailing content");
    }
    return value;
  };

  const escapePythonJsonString = (value) =>
    JSON.stringify(value).replace(/[^\x00-\x7F]/g, (char) =>
      char.split("")
        .map((codePoint) =>
          `\\u${codePoint.charCodeAt(0).toString(16).padStart(4, "0")}`
        )
        .join("")
    );

  const canonicalize = (obj) => {
    const serialize = (value) => {
      if (
        value &&
        typeof value === "object" &&
        Object.keys(value).length === 1 &&
        typeof value.__reportNumberToken === "string"
      ) {
        return value.__reportNumberToken;
      }
      if (value === null) return "null";
      if (typeof value === "string") return escapePythonJsonString(value);
      if (typeof value === "boolean") return value ? "true" : "false";
      if (Array.isArray(value)) {
        return `[${value.map(serialize).join(",")}]`;
      }
      const keys = Object.keys(value).sort();
      return `{${keys
        .map((key) => `${escapePythonJsonString(key)}:${serialize(value[key])}`)
        .join(",")}}`;
    };
    return serialize(stripExcluded(obj));
  };

  const handleVerify = async () => {
    if (!file || !sessionIdInput) return;
    setVerifying(true);
    setResult(null);

    try {
      const text = await file.text();
      const parsed = parseJsonWithNumberTokens(text);
      const canonical = canonicalize(parsed);
      const encoder = new TextEncoder();
      const buffer = await crypto.subtle.digest(
        "SHA-256",
        encoder.encode(canonical)
      );
      const hashArray = Array.from(new Uint8Array(buffer));
      const localHash =
        "sha256:" +
        hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");

      const ok = await service.verifyReportHash(
        sessionIdInput.trim(),
        localHash
      );
      setResult({
        ok,
        message: ok
          ? "Report hash verified — the local report matches the on-chain record."
          : "Report hash mismatch — the local report does not match the on-chain record.",
      });
    } catch (err) {
      if (err.code === "SESSION_NOT_FOUND") {
        setResult({
          ok: false,
          message: "Session not found on the blockchain. Check the session ID.",
        });
        return;
      }
      setResult({
        ok: false,
        message: "Verification error: " + (err.message || String(err)),
      });
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div>
      <h2 className="text-xl font-semibold">Check a report file</h2>
      <p className="mt-1 text-sm text-slate-600">
        Choose your local <code>-report.json</code>. The browser computes its SHA-256 hash and compares it with the hash stored
        on-chain. The file never leaves your device.
      </p>

      <div className="mt-5 grid gap-4">
        <div>
          <label htmlFor="rh-session" className="label">Session id (UUID)</label>
          <input
            id="rh-session"
            type="text"
            value={sessionIdInput}
            onChange={(e) => setSessionIdInput(e.target.value)}
            placeholder="a1808a9e-068f-45b2-a33a-ba79e6518739"
            className="input font-mono"
            disabled={verifying || Boolean(sessionId)}
          />
        </div>
        <div>
          <label htmlFor="rh-file" className="label">Report file</label>
          <input
            id="rh-file"
            type="file"
            accept=".json"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            disabled={verifying}
            className="input file:mr-3 file:rounded-md file:border-0 file:bg-ink file:px-3 file:py-1 file:text-xs file:font-semibold file:text-white"
          />
          {file && <p className="mt-1.5 text-xs text-slate-500">Selected: {file.name} ({Math.round(file.size / 1024)} KB)</p>}
        </div>
        <div>
          <button onClick={handleVerify} disabled={verifying || !file || !sessionIdInput} className="btn-primary">
            {verifying ? "Checking…" : "Check report hash"}
          </button>
        </div>
      </div>

      {result && (
        <div role="status" className={`mt-5 flex items-start gap-3 rounded-lg p-4 text-sm ${result.ok ? "bg-emerald-50 text-emerald-900" : "bg-rose-50 text-rose-900"}`}>
          <Status state={result.ok} />
          <span className="pt-0.5">{result.message}</span>
        </div>
      )}

      <details className="note mt-5">
        <summary className="cursor-pointer font-medium text-slate-700">How the hash is computed</summary>
        <p className="mt-2">
          The dashboard parses your <code>-report.json</code>, removes <code>report_hash</code> and <code>generated_at</code> (matching
          the Python pipeline&rsquo;s <code>_compute_hash</code>), serialises canonical JSON with sorted keys and no whitespace, and
          computes SHA-256 in the browser. That hash is compared with the <code>reportHash</code> stored on-chain, so any local edit
          to the score, grade or notes makes the check fail.
        </p>
      </details>
    </div>
  );
}
