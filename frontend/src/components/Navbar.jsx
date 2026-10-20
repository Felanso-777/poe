import { Link, useNavigate } from "react-router-dom";
import { useBlockchain } from "../context/BlockchainContext";
import { useAuth } from "../context/AuthContext";
import Fingerprint from "./Fingerprint";

export default function Navbar() {
  const { demo, connect, disconnect, status, error } = useBlockchain();
  const { user, role, fullName, signOut, loading: authLoading } = useAuth();
  const navigate = useNavigate();

  const canConnect = demo || status === "disconnected" || status === "error";
  const label = demo ? "Demo mode" : status === "connected" ? "Local chain connected" : status;
  const dot = demo ? "bg-amber-400" : status === "connected" ? "bg-emerald-500" : status === "error" ? "bg-rose-500" : "bg-slate-400";

  const handleSignOut = async () => {
    const { error } = await signOut();
    if (!error) {
      navigate("/login", { replace: true });
    }
  };

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-chalk/85 backdrop-blur">
      <div className="mx-auto flex max-w-[1440px] items-center justify-between px-4 py-3 sm:px-6 lg:px-10">
        <div className="flex items-center gap-3">
          <Fingerprint value="proof-of-effort" cells={5} big />
          <div className="leading-tight">
            <p className="font-display text-lg font-semibold tracking-tight">Proof of Effort</p>
            <p className="text-xs text-slate-500">AuditLedger dashboard</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="hidden items-center gap-2 text-sm text-slate-600 sm:inline-flex">
            <span className={`h-2 w-2 rounded-full ${dot}`} />
            {label}
          </span>

          {user ? (
            <div className="flex items-center gap-3 border-l border-slate-300 pl-4">
              <div className="hidden sm:flex items-center gap-1 text-xs text-slate-500">
                <span className="font-medium text-slate-700">{fullName || "User"}</span>
                <span className="hidden sm:block">·</span>
                <span
                  className={`px-1.5 py-0.5 rounded-full text-xs font-medium ${
                    role === "admin"
                      ? "bg-amber-100 text-amber-800"
                      : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {role}
                </span>
              </div>
              <button
                onClick={handleSignOut}
                disabled={authLoading}
                className="px-3 py-1.5 rounded-md text-sm font-medium text-rose-600 hover:bg-rose-50 hover:underline transition-colors disabled:opacity-50"
              >
                {authLoading ? "Signing out…" : "Sign out"}
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 border-l border-slate-300 pl-4">
              <Link
                to="/login"
                className="px-3 py-1.5 rounded-md text-sm font-medium text-poe-600 hover:text-poe-700 hover:underline transition-colors"
              >
                Sign in
              </Link>
              <Link
                to="/register"
                className="px-3 py-1.5 rounded-md text-sm font-medium bg-poe-600 text-white hover:bg-poe-700 hover:no-underline transition-colors"
              >
                Create account
              </Link>
            </div>
          )}

          <button
            onClick={() => (canConnect ? connect() : disconnect())}
            disabled={status === "connecting"}
            title={error || undefined}
            className="btn-ghost !py-2"
          >
            {status === "connecting" ? "Connecting…" : canConnect ? "Connect" : "Disconnect"}
          </button>
        </div>
      </div>
    </header>
  );
}
