/**
 * config.js — Frontend configuration loaded from environment variables.
 *
 * Required (set in .env, copied from .env.example):
 *   VITE_POE_RPC_URL        JSON-RPC endpoint (Hardhat: http://127.0.0.1:8545)
 *   VITE_POE_CONTRACT_ADDRESS Deployed AuditLedger address
 *   VITE_POE_CHAIN_ID       Chain id (Hardhat: 31337)
 *
 * Optional:
 *   VITE_DEMO_MODE          "true" → use mock data, no blockchain connection
 *
 * No private keys are ever read by the frontend.
 */

export const RPC_URL = import.meta.env.VITE_POE_RPC_URL || "http://127.0.0.1:8545";
export const CONTRACT_ADDRESS =
  import.meta.env.VITE_POE_CONTRACT_ADDRESS || "";
export const CHAIN_ID = Number(import.meta.env.VITE_POE_CHAIN_ID || 31337);
export const DEMO_MODE =
  import.meta.env.VITE_DEMO_MODE === "true";

export function isConfigured() {
  return Boolean(CONTRACT_ADDRESS && CONTRACT_ADDRESS !== "0xREPLACE_WITH_DEPLOYED_CONTRACT_ADDRESS");
}

export function requiredEnvMissing() {
  const missing = [];
  if (!CONTRACT_ADDRESS || CONTRACT_ADDRESS === "0xREPLACE_WITH_DEPLOYED_CONTRACT_ADDRESS") {
    missing.push("VITE_POE_CONTRACT_ADDRESS");
  }
  return missing;
}
