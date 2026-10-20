import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Fingerprint from "../components/Fingerprint";

export default function Login() {
  const [form, setForm] = useState({ email: "", password: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const { signIn } = useAuth();
  const navigate = useNavigate();

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg("");
    setLoading(true);
    try {
      const { error } = await signIn(form.email, form.password);
      if (error) {
        setErrorMsg(error.message);
      } else {
        navigate("/", { replace: true });
      }
    } catch (err) {
      setErrorMsg(err.message || "Sign in failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-chalk pb-10 sm:pb-0">
      <div className="w-full max-w-md px-4 sm:px-6 lg:px-8">
        <div className="bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
          {/* Header */}
          <div className="bg-white px-6 py-6 border-b border-slate-200">
            <div className="flex items-center gap-3 mb-2">
              <Fingerprint value="proof-of-effort-login" cells={6} big />
              <div className="leading-tight">
                <h2 className="font-display text-lg font-semibold text-slate-900 tracking-tight">
                  Welcome back
                </h2>
                <p className="text-xs text-slate-500">Sign in to your account</p>
              </div>
            </div>
          </div>

          {/* Form Body */}
          <div className="p-6 space-y-5">
            {errorMsg && (
              <div className="rounded-lg bg-rose-50 border border-rose-200 p-3 text-sm text-rose-800">
                {errorMsg}
              </div>
            )}
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-slate-700 mb-1">
                  Email address
                </label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={form.email}
                  onChange={handleChange}
                  className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-poe-500 focus:border-transparent outline-none transition-all"
                  placeholder="you@company.com"
                />
              </div>

              <div className="relative">
                <label htmlFor="password" className="block text-sm font-medium text-slate-700 mb-1">
                  Password
                </label>
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={form.password}
                  onChange={handleChange}
                  className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-poe-500 focus:border-transparent outline-none transition-all pr-10"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  {showPassword ? "🙈" : "👁️"}
                </button>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <input
                    id="remember-me"
                    name="remember-me"
                    type="checkbox"
                    className="h-4 w-4 text-poe-600 focus:ring-poe-500 border-slate-300 rounded"
                  />
                  <label htmlFor="remember-me" className="ml-2 text-sm text-slate-600">
                    Remember me
                  </label>
                </div>
                <a href="#" className="text-sm text-poe-600 hover:text-poe-700 font-medium">
                  Forgot password?
                </a>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full flex justify-center py-3 px-4 border border-transparent rounded-lg shadow-sm text-sm font-semibold text-white bg-poe-600 hover:bg-poe-700 disabled:bg-slate-300 disabled:text-slate-500 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-poe-500 transition-all active:scale-95"
              >
                {loading ? "Signing in…" : "Sign in"}
              </button>
            </form>

            {/* Footer link */}
            <p className="mt-8 text-center text-sm text-slate-600">
              Don't have an account?{" "}
              <Link to="/register" className="font-medium text-poe-600 hover:text-poe-700 transition-colors">
                Create account
              </Link>
            </p>
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-slate-200 text-center">
            <p className="text-xs text-slate-400">
              Proof of Effort &middot; Privacy-first effort tracking
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
