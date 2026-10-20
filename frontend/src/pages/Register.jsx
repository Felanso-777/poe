import { useState } from "react";
import { Link } from "react-router-dom";
import Fingerprint from "../components/Fingerprint";

export default function Register() {
  const [form, setForm] = useState({
    fullName: "",
    email: "",
    password: "",
    confirmPassword: "",
  });
  const [terms, setTerms] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    if (type === "checkbox") {
      setTerms(checked);
    } else {
      setForm({ ...form, [name]: value });
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    // TODO: Connect to Supabase auth later
    alert("Create account clicked: " + form.email);
  };

  const passwordsMatch = form.password === form.confirmPassword;

  return (
    <div className="min-h-screen flex items-center justify-center bg-chalk pb-10 sm:pb-0">
      <div className="w-full max-w-md px-4 sm:px-6 lg:px-8">
        <div className="bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
          {/* Header */}
          <div className="bg-white px-6 py-6 border-b border-slate-200">
            <div className="flex items-center gap-3 mb-2">
              <Fingerprint value="proof-of-effort-register" cells={6} big />
              <div className="leading-tight">
                <h2 className="font-display text-lg font-semibold text-slate-900 tracking-tight">
                  Create account
                </h2>
                <p className="text-xs text-slate-500">Join Proof of Effort today</p>
              </div>
            </div>
          </div>

          {/* Form Body */}
          <div className="p-6 space-y-4">
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="fullName" className="block text-sm font-medium text-slate-700 mb-1">
                  Full name
                </label>
                <input
                  id="fullName"
                  name="fullName"
                  type="text"
                  autoComplete="name"
                  required
                  value={form.fullName}
                  onChange={handleChange}
                  className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-poe-500 focus:border-transparent outline-none transition-all"
                  placeholder="John Doe"
                />
              </div>

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
                  autoComplete="new-password"
                  required
                  value={form.password}
                  minLength={6}
                  onChange={handleChange}
                  className={`w-full px-3.5 py-2.5 border rounded-lg focus:ring-2 focus:ring-poe-500 focus:border-transparent outline-none transition-all pr-10 ${
                    form.password.length > 0 && !passwordsMatch
                      ? "border-red-500 focus:ring-red-500"
                      : "border-slate-300"
                  }`}
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  {showPassword ? "🙈" : "👁️"}
                </button>
                {form.password.length > 0 && !passwordsMatch && (
                  <p className="text-xs text-red-600 mt-1">Passwords do not match</p>
                )}
              </div>

              <div className="relative">
                <label htmlFor="confirmPassword" className="block text-sm font-medium text-slate-700 mb-1">
                  Confirm password
                </label>
                <input
                  id="confirmPassword"
                  name="confirmPassword"
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  required
                  value={form.confirmPassword}
                  onChange={handleChange}
                  className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-poe-500 focus:border-transparent outline-none transition-all"
                  placeholder="••••••••"
                />
              </div>

              <div className="flex items-start">
                <input
                  id="terms"
                  name="terms"
                  type="checkbox"
                  required
                  checked={terms}
                  onChange={handleChange}
                  className="h-4 w-4 mt-0.5 text-poe-600 focus:ring-poe-500 border-slate-300 rounded"
                />
                <label htmlFor="terms" className="ml-2 text-sm text-slate-600 leading-6">
                  I agree to the{" "}
                  <a href="#" className="text-poe-600 hover:text-poe-700 font-medium">
                    Terms of Service
                  </a>{" "}
                  and{" "}
                  <a href="#" className="text-poe-600 hover:text-poe-700 font-medium">
                    Privacy Policy
                  </a>
                </label>
              </div>

              <button
                type="submit"
                disabled={!terms || !passwordsMatch || form.password.length < 6}
                className="w-full flex justify-center py-3 px-4 border border-transparent rounded-lg shadow-sm text-sm font-semibold text-white bg-poe-600 hover:bg-poe-700 disabled:bg-slate-300 disabled:text-slate-500 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-poe-500 transition-all active:scale-95"
              >
                Create account
              </button>
            </form>

            {/* Footer link */}
            <p className="mt-8 text-center text-sm text-slate-600">
              Already have an account?{" "}
              <Link to="/login" className="font-medium text-poe-600 hover:text-poe-700 transition-colors">
                Sign in
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
