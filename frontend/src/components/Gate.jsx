import { useBlockchain } from "../context/BlockchainContext";
import LoadingSpinner from "./LoadingSpinner";
import ErrorMessage from "./ErrorMessage";
import EmptyState from "./EmptyState";

/** Shows loading / error / not-connected states, otherwise renders children. */
export default function Gate({ loading, error, status, onRetry, children }) {
  const { connect } = useBlockchain();
  if (loading) return <LoadingSpinner message="Loading from the ledger…" />;
  if (error) return <ErrorMessage message={error} onRetry={onRetry} />;
  if (status !== "connected") {
    return (
      <EmptyState
        title="Not connected to the ledger"
        description="Connect to load sessions from the AuditLedger contract."
        action={<button className="btn-primary" onClick={() => connect()}>Connect</button>}
      />
    );
  }
  return children;
}
