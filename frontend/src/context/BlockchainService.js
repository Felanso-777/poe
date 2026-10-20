import { ethers } from "ethers";
import {
  RPC_URL,
  CONTRACT_ADDRESS,
  CHAIN_ID,
  DEMO_MODE,
  isConfigured,
} from "../config";
import { AUDIT_LEDGER_ABI } from "../abi";

function isSessionNotFoundError(error) {
  const details = [
    error?.code,
    error?.name,
    error?.shortMessage,
    error?.message,
    error?.info?.error?.message,
    error?.info?.error?.data,
  ]
    .filter(Boolean)
    .join(" ");
  return /SessionNotFound|session not found/i.test(details);
}

/**
 * BlockchainContext provides:
 *   - provider / signer (read-only; no private keys in frontend)
 *   - contract instance
 *   - connection status (connecting, connected, error, disconnected)
 *   - demo-mode flag
 *   - session helpers that mirror the Python pipeline's encoding:
 *       sessionIdBytes32(uuid)   -> ethers keccak256 of UTF-8 UUID
 *   - event listening for SessionRecorded
 */

const DEMO_SESSIONS = [
  {
    id: "demo-session-001",
    sessionIdBytes32: ethers.keccak256(ethers.toUtf8Bytes("demo-session-001")),
    merkleRoot:
      "0x" + "a1".repeat(32),
    timestamp: Date.now() / 1000 - 3600,
    submitter: "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
    txHash: "0x" + "b2".repeat(32),
    score: 87,
    grade: "B",
    verified: true,
    classification: "inconclusive",
    confidence: 0,
    modelVersion: "logistic-baseline-1.0",
    featureVersion: "2.0",
    synthetic: true,
    warnings: ["Synthetic demo data is not real evidence."],
  },
  {
    id: "demo-session-002",
    sessionIdBytes32: ethers.keccak256(ethers.toUtf8Bytes("demo-session-002")),
    merkleRoot:
      "0x" + "c3".repeat(32),
    timestamp: Date.now() / 1000 - 7200,
    submitter: "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
    txHash: "0x" + "c4".repeat(32),
    score: 64,
    grade: "D",
    verified: true,
    classification: "inconclusive",
    confidence: 0,
    modelVersion: "logistic-baseline-1.0",
    featureVersion: "2.0",
    synthetic: true,
    warnings: ["Synthetic demo data is not real evidence."],
  },
];

export class BlockchainService {
  constructor() {
    this.provider = null;
    this.signer = null;
    this.contract = null;
    this.status = "disconnected"; // connecting | connected | error | disconnected
    this.error = null;
    this.network = null;
    this.account = null;
    this.listeners = [];
    this.demo = DEMO_MODE;
    this._demoSessions = [...DEMO_SESSIONS];
  }

  async connect() {
    if (this.demo) {
      this.status = "connected";
      this.network = { name: "Demo Mode (mock)", chainId: 0 };
      this.account = "0xdemo";
      this.error = null;
      return;
    }

    this.status = "connecting";
    this.error = null;

    try {
      if (!isConfigured()) {
        throw new Error(
          "Contract address not configured. Set VITE_POE_CONTRACT_ADDRESS in .env (copy from .env.example)."
        );
      }

      this.provider = new ethers.JsonRpcProvider(RPC_URL, CHAIN_ID);
      this.network = await this.provider.getNetwork();
      this.contract = new ethers.Contract(
        CONTRACT_ADDRESS,
        AUDIT_LEDGER_ABI,
        this.provider
      );
      this.signer = null;
      this.account = null;
      this.status = "connected";
      this.error = null;

      this._startEventListener();
    } catch (err) {
      this.status = "error";
      this.error = err.message || String(err);
      this.provider = null;
      this.contract = null;
      throw err;
    }
  }

  disconnect() {
    this._stopEventListener();
    this.provider = null;
    this.signer = null;
    this.contract = null;
    this.status = "disconnected";
    this.account = null;
    this.network = null;
    this.error = null;
  }

  // ---------- encoding helpers matching the Python pipeline ----------

  sessionIdBytes32(uuidString) {
    if (ethers.isHexString(uuidString, 32)) {
      return ethers.hexlify(uuidString);
    }
    return ethers.keccak256(ethers.toUtf8Bytes(uuidString));
  }

  merkleRootBytes32(root) {
    const value = root.trim();
    const normalized = value.startsWith("0x") ? value : `0x${value}`;
    if (!ethers.isHexString(normalized, 32)) {
      throw new Error(
        "Merkle root must be exactly 64 hexadecimal characters, with or without the 0x prefix."
      );
    }
    return normalized;
  }

  // ---------- read operations ----------

  async sessionExists(uuidString) {
    if (this.demo) {
      return this._demoSessions.some((s) => s.id === uuidString);
    }
    const bytes32 = this.sessionIdBytes32(uuidString);
    return this.contract.sessionExists(bytes32);
  }

  async getSession(uuidString) {
    if (this.demo) {
      const found = this._demoSessions.find((s) => s.id === uuidString);
      if (!found) throw new Error("Session not found");
      return {
        sessionId: found.sessionIdBytes32,
        merkleRoot: found.merkleRoot,
        timestamp: Number(found.timestamp) * 1000, // ms
        submitter: found.submitter,
        reportHash: found.reportHash || "",
        modelVersion: found.modelVersion || "unknown",
        featureVersion: found.featureVersion || "unknown",
        score: found.score,
        grade: found.grade,
        classification: found.classification,
        confidence: found.confidence,
        synthetic: found.synthetic,
      };
    }
    const bytes32 = this.sessionIdBytes32(uuidString);
    const result = await this.contract.getSession(bytes32);
    const session =
      result.session ||
      (result.length === 1 && result[0] && typeof result[0] === "object"
        ? result[0]
        : result);
    // ethers v6 returns BigInt for uint256 and bytes32 as hex string
    return {
      sessionId: session.sessionId,
      merkleRoot: session.merkleRoot,
      timestamp: Number(session.timestamp) * 1000,
      submitter: session.submitter,
      reportHash: session.reportHash || "",
      modelVersion: session.modelVersion || "unknown",
      featureVersion: session.featureVersion || "unknown",
      score: Number(session.heuristicScoreBps || 0) / 100,
      classification: session.mlClassification || "inconclusive",
      confidence: Number(session.mlConfidenceBps || 0) / 10000,
      synthetic: Boolean(session.synthetic),
    };
  }

  async verifyMerkleRoot(uuidString, merkleRootHex) {
    const normalizedRoot = this.merkleRootBytes32(merkleRootHex);
    if (this.demo) {
      const found = this._demoSessions.find((s) => s.id === uuidString);
      return found
        ? found.merkleRoot.toLowerCase() === normalizedRoot.toLowerCase()
        : false;
    }
    const bytes32 = this.sessionIdBytes32(uuidString);
    return this.contract.verifyMerkleRoot(bytes32, normalizedRoot);
  }

  // ---------- sessions list (from events + getSession) ----------

  async fetchAllSessions() {
    if (this.demo) {
      return this._demoSessions.map((s) => ({
        id: s.id,
        sessionId: s.sessionIdBytes32,
        merkleRoot: s.merkleRoot,
        timestamp: Number(s.timestamp) * 1000,
        submitter: s.submitter,
        txHash: s.txHash,
        score: s.score,
        grade: s.grade,
        verified: s.verified,
        demo: true,
        classification: s.classification,
        confidence: s.confidence,
        modelVersion: s.modelVersion,
        featureVersion: s.featureVersion,
        synthetic: s.synthetic,
        warnings: s.warnings,
      }));
    }

    if (!this.contract) throw new Error("Contract not connected");

    // Query past SessionRecorded events to discover session ids
    const filter = this.contract.filters.SessionRecorded();
    const events = await this.contract.queryFilter(filter, 0, "latest");

    const sessions = [];
    for (const ev of events) {
      const sessionIdBytes = ev.args.sessionId;
      const merkleRoot = ev.args.merkleRoot;
      const timestamp = Number(ev.args.timestamp) * 1000;
      const submitter = ev.args.submitter;
      const txHash = ev.transactionHash;

      // Fetch full record to confirm and get submitter
      let score = null;
      let grade = null;
      let verified = false;
      let record = null;
      try {
        record = await this.getSession(sessionIdBytes);
        verified = await this.contract.verifyMerkleRoot(
          sessionIdBytes,
          record.merkleRoot
        );
      } catch (e) {
        // Keep the event visible even if the full record cannot be read.
        console.warn("Unable to load session record", sessionIdBytes, e);
      }

      sessions.push({
        id: sessionIdBytes, // display as hex
        sessionId: sessionIdBytes,
        merkleRoot,
        timestamp,
        submitter,
        txHash,
        score,
        grade,
        verified: record ? verified : null,
        reportHash: record?.reportHash || "",
        modelVersion: record?.modelVersion || "unknown",
        featureVersion: record?.featureVersion || "unknown",
        score: record ? Number(record.heuristicScoreBps || 0) / 100 : null,
        classification: record?.mlClassification || "inconclusive",
        confidence: record ? Number(record.mlConfidenceBps || 0) / 10000 : null,
        synthetic: Boolean(record?.synthetic),
        warnings: [],
        demo: false,
      });
    }

    // Sort newest first
    sessions.sort((a, b) => b.timestamp - a.timestamp);
    return sessions;
  }

  // ---------- report hash verification ----------

  async verifyReportHash(sessionId, localHash) {
    if (this.demo) {
      const session = this._demoSessions.find((s) => s.id === sessionId);
      if (!session) return false;
      const normalizeHash = (hash) =>
        hash.startsWith("sha256:")
          ? `0x${hash.slice(7)}`
          : hash.startsWith("0x")
          ? hash
          : `0x${hash}`;
      return normalizeHash(session.reportHash || "").toLowerCase() ===
        normalizeHash(localHash).toLowerCase();
    }

    if (!this.contract) throw new Error("Contract not connected");

    // Convert sessionId string (UUID) to bytes32 via keccak256
    const sessionIdBytes = this.sessionIdBytes32(sessionId);

    let record;
    try {
      record = await this.contract.getSession(sessionIdBytes);
    } catch (error) {
      if (isSessionNotFoundError(error)) {
        const notFoundError = new Error(
          "Session not found on the blockchain. Check the session ID."
        );
        notFoundError.code = "SESSION_NOT_FOUND";
        throw notFoundError;
      }
      throw error;
    }
    const onChainHash = record.reportHash; // bytes32 hex from contract

    // Normalize both hashes to 0x-prefixed hex for comparison
    const onChainHashHex = onChainHash.startsWith("0x")
      ? onChainHash
      : "0x" + onChainHash;

    const localHashHex = localHash.startsWith("sha256:")
      ? "0x" + localHash.slice(7)
      : localHash.startsWith("0x")
      ? localHash
      : "0x" + localHash;

    return onChainHashHex.toLowerCase() === localHashHex.toLowerCase();
  }

  // ---------- event listener ----------

  _startEventListener() {
    if (!this.contract || this.demo) return;
    this._stopEventListener();
    const filter = this.contract.filters.SessionRecorded();
    this.contract.on(filter, (sessionId, merkleRoot, submitter, timestamp, event) => {
      this.listeners.forEach((cb) => {
        cb({
          sessionId,
          merkleRoot,
          submitter,
          timestamp: Number(timestamp) * 1000,
          txHash: event.transactionHash,
        });
      });
    });
  }

  _stopEventListener() {
    if (this.contract) {
      try {
        this.contract.removeAllListeners("SessionRecorded");
      } catch (_) {
        // ignore
      }
    }
  }

  onSessionRecorded(cb) {
    this.listeners.push(cb);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== cb);
    };
  }
}

export const blockchainService = new BlockchainService();
