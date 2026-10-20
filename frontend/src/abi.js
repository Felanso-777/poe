/**
 * abi.js — AuditLedger contract ABI.
 *
 * Extracted from the Hardhat compilation artifact:
 *   blockchain/artifacts/contracts/AuditLedger.sol/AuditLedger.json
 *
 * Re-copy this array whenever the contract is recompiled and the ABI changes.
 */

export const AUDIT_LEDGER_ABI = [
  {
    "inputs": [
      { "internalType": "bytes32", "name": "sessionId", "type": "bytes32" },
      { "internalType": "bytes32", "name": "merkleRoot", "type": "bytes32" },
      { "internalType": "bytes32", "name": "reportHash", "type": "bytes32" },
      { "internalType": "string", "name": "modelVersion", "type": "string" },
      { "internalType": "string", "name": "featureVersion", "type": "string" },
      { "internalType": "uint256", "name": "heuristicScoreBps", "type": "uint256" },
      { "internalType": "string", "name": "mlClassification", "type": "string" },
      { "internalType": "uint256", "name": "mlConfidenceBps", "type": "uint256" },
      { "internalType": "bool", "name": "synthetic", "type": "bool" }
    ],
    "name": "submitSessionWithAnalysis",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function",
  },
  {
    "inputs": [
      { "internalType": "bytes32", "name": "sessionId", "type": "bytes32" },
      { "internalType": "bytes32", "name": "merkleRoot", "type": "bytes32" },
      { "internalType": "bytes32", "name": "reportHash", "type": "bytes32" },
      { "internalType": "string", "name": "modelVersion", "type": "string" },
      { "internalType": "string", "name": "featureVersion", "type": "string" }
    ],
    "name": "submitSessionWithMetadata",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function",
  },
  {
    "inputs": [],
    "stateMutability": "nonpayable",
    "type": "constructor",
  },
  {
    "inputs": [
      { "internalType": "bytes32", "name": "sessionId", "type": "bytes32" },
    ],
    "name": "DuplicateSession",
    "type": "error",
  },
  {
    "inputs": [],
    "name": "NotAuthorized",
    "type": "error",
  },
  {
    "inputs": [],
    "name": "NotOwner",
    "type": "error",
  },
  {
    "inputs": [
      { "internalType": "bytes32", "name": "sessionId", "type": "bytes32" },
    ],
    "name": "SessionNotFound",
    "type": "error",
  },
  {
    "inputs": [],
    "name": "ZeroMerkleRoot",
    "type": "error",
  },
  {
    "inputs": [],
    "name": "ZeroSessionId",
    "type": "error",
  },
  {
    "anonymous": false,
    "inputs": [
      { "indexed": true, "internalType": "bytes32", "name": "sessionId", "type": "bytes32" },
      { "indexed": false, "internalType": "bytes32", "name": "merkleRoot", "type": "bytes32" },
      { "indexed": true, "internalType": "address", "name": "submitter", "type": "address" },
      { "indexed": false, "internalType": "uint256", "name": "timestamp", "type": "uint256" },
    ],
    "name": "SessionRecorded",
    "type": "event",
  },
  {
    "inputs": [
      { "internalType": "bytes32", "name": "sessionId", "type": "bytes32" },
      { "internalType": "bytes32", "name": "merkleRoot", "type": "bytes32" },
    ],
    "name": "submitSession",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function",
  },
  {
    "inputs": [],
    "name": "owner",
    "outputs": [{ "internalType": "address", "name": "", "type": "address" }],
    "stateMutability": "view",
    "type": "function",
  },
  {
    "inputs": [
      { "internalType": "bytes32", "name": "sessionId", "type": "bytes32" },
    ],
    "name": "getSession",
    "outputs": [
      {
        "components": [
          { "internalType": "bytes32", "name": "sessionId", "type": "bytes32" },
          { "internalType": "bytes32", "name": "merkleRoot", "type": "bytes32" },
          { "internalType": "bytes32", "name": "reportHash", "type": "bytes32" },
          { "internalType": "string", "name": "modelVersion", "type": "string" },
          { "internalType": "string", "name": "featureVersion", "type": "string" },
          { "internalType": "uint256", "name": "heuristicScoreBps", "type": "uint256" },
          { "internalType": "string", "name": "mlClassification", "type": "string" },
          { "internalType": "uint256", "name": "mlConfidenceBps", "type": "uint256" },
          { "internalType": "bool", "name": "synthetic", "type": "bool" },
          { "internalType": "uint256", "name": "timestamp", "type": "uint256" },
          { "internalType": "address", "name": "submitter", "type": "address" }
        ],
        "internalType": "struct AuditLedger.Session",
        "name": "session",
        "type": "tuple"
      }
    ],
    "stateMutability": "view",
    "type": "function",
  },
  {
    "inputs": [
      { "internalType": "bytes32", "name": "sessionId", "type": "bytes32" },
    ],
    "name": "isAuthorized",
    "outputs": [{ "internalType": "bool", "name": "", "type": "bool" }],
    "stateMutability": "view",
    "type": "function",
  },
  {
    "inputs": [
      { "internalType": "bytes32", "name": "sessionId", "type": "bytes32" },
      { "internalType": "bytes32", "name": "root", "type": "bytes32" },
    ],
    "name": "verifyMerkleRoot",
    "outputs": [{ "internalType": "bool", "name": "", "type": "bool" }],
    "stateMutability": "view",
    "type": "function",
  },
  {
    "inputs": [
      { "internalType": "bytes32", "name": "sessionId", "type": "bytes32" },
    ],
    "name": "sessionExists",
    "outputs": [{ "internalType": "bool", "name": "", "type": "bool" }],
    "stateMutability": "view",
    "type": "function",
  },
];
