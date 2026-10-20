import { useBlockchain } from "../context/BlockchainContext";

const dots = { connected: "bg-emerald-500", connecting: "bg-amber-400", error: "bg-rose-500", disconnected: "bg-slate-400" };

/** Read-only RPC connection summary. No private keys are ever shown. */
export default function ConnectionStatus() {
  const { status, error, network, account, demo, connect, disconnect } = useBlockchain();
  const canConnect = demo || status === "disconnected" || status === "error";
  const networkLabel = demo
    ? "Demo (mock)"
    : network?.name && network.name !== "unknown"
    ? network.name
    : "Hardhat Localhost";

  const rows = [
    ["Network", networkLabel],
    ["Chain ID", demo ? "0 (mock)" : network ? network.chainId.toString() : "31337"],
    ["Account", demo ? "Simulated" : account || "Read-only"],
  ];

  return (
    <section className="card p-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-base font-semibold">Ledger connection</h3>
        <span className="inline-flex items-center gap-2 text-sm text-slate-600">
          <span className={`h-2 w-2 rounded-full ${demo ? "bg-amber-400" : dots[status]}`} />
          {demo ? "Demo mode" : status}
        </span>
      </div>
      {demo && <p className="mt-2 text-sm text-slate-600">Demo mode is on. Data is simulated and nothing is read from the chain.</p>}
      <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-3">
        {rows.map(([k, v]) => (
          <div key={k} className="min-w-0">
            <dt className="text-slate-500">{k}</dt>
            <dd className="mt-0.5 truncate font-medium" title={v}>{v}</dd>
          </div>
        ))}
      </dl>
      {error && <p role="alert" className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
      <button
        onClick={() => (canConnect ? connect() : disconnect())}
        disabled={status === "connecting"}
        className="btn-ghost mt-5"
      >
        {status === "connecting" ? "Connecting…" : canConnect ? "Connect" : "Disconnect"}
      </button>
    </section>
  );
}
