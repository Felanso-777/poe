import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { supabase } from "../lib/supabase";

export default function Profile() {
  const { user, loading: authLoading } = useAuth();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (authLoading || !user) return;
    const fetchProfile = async () => {
      try {
        setLoading(true);
        const { data, error } = await supabase
          .from("profiles")
          .select("*")
          .eq("id", user.id)
          .single();
        if (error) throw error;
        setProfile(data);
      } catch (err) {
        setError(err.message || "Failed to load profile");
      } finally {
        setLoading(false);
      }
    };
    fetchProfile();
  }, [user, authLoading]);

  if (authLoading || loading) {
    return (
      <div className="mx-auto max-w-2xl py-12 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 rounded-full border-4 border-slate-200 border-t-slate-600 animate-spin" />
          <p className="text-sm text-slate-500">Loading profile…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl py-12">
        <div className="card p-6 text-center">
          <h2 className="text-lg font-semibold text-slate-900">Unable to load profile</h2>
          <p className="mt-2 text-sm text-slate-600">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium text-poe-600 hover:text-poe-700 hover:underline transition-colors"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="mx-auto max-w-2xl py-12">
        <div className="card p-6 text-center">
          <h2 className="text-lg font-semibold text-slate-900">No profile found</h2>
          <p className="mt-2 text-sm text-slate-600">
            No profile record exists for your account yet.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Profile</h1>
          <p className="mt-2 text-slate-600">
            Your account details. These come from your Supabase profile record.
          </p>
        </div>
        <Link to="/" className="btn-ghost">Back to dashboard</Link>
      </header>

      <section className="card p-6">
        <div className="flex flex-col sm:flex-row sm:items-center gap-6">
          <div className="flex items-center gap-2 text-xs text-slate-500 font-medium">
            <span
              className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                profile.role === "admin"
                  ? "bg-amber-100 text-amber-800 border border-amber-200"
                  : "bg-slate-100 text-slate-600 border border-slate-200"
              }`}
            >
              {profile.role}
            </span>
            <span className="hidden sm:block">·</span>
            <span>{new Date(profile.created_at).toLocaleDateString()}</span>
          </div>
        </div>

        <dl className="mt-6 divide-y divide-slate-200">
          <div className="grid gap-1 py-3 sm:grid-cols-[11rem_1fr] sm:gap-4">
            <dt className="text-sm text-slate-500">Email</dt>
            <dd className="min-w-0 break-all text-sm font-medium">{user.email}</dd>
          </div>
          <div className="grid gap-1 py-3 sm:grid-cols-[11rem_1fr] sm:gap-4">
            <dt className="text-sm text-slate-500">Full name</dt>
            <dd className="min-w-0 break-all text-sm">
              {profile.full_name || <span className="text-slate-400">— not set —</span>}
            </dd>
          </div>
          <div className="grid gap-1 py-3 sm:grid-cols-[11rem_1fr] sm:gap-4">
            <dt className="text-sm text-slate-500">Role</dt>
            <dd className="min-w-0 break-all text-sm">
              <span
                className={`px-1.5 py-0.5 rounded-full text-xs font-medium ${
                  profile.role === "admin"
                    ? "bg-amber-100 text-amber-800 border border-amber-200"
                    : "bg-slate-100 text-slate-600 border border-slate-200"
                }`}
              >
                {profile.role}
              </span>
            </dd>
          </div>
          <div className="grid gap-1 py-3 sm:grid-cols-[11rem_1fr] sm:gap-4">
            <dt className="text-sm text-slate-500">Member since</dt>
            <dd className="min-w-0 break-all text-sm font-mono">
              {new Date(profile.created_at).toLocaleString()}
            </dd>
          </div>
          <div className="grid gap-1 py-3 sm:grid-cols-[11rem_1fr] sm:gap-4">
            <dt className="text-sm text-slate-500">User ID</dt>
            <dd className="min-w-0 break-all text-sm font-mono text-slate-500">
              {profile.id}
            </dd>
          </div>
        </dl>
      </section>

      <section className="card p-6">
        <h2 className="text-lg font-semibold mb-4">Account notes</h2>
        <ul className="space-y-3 text-sm text-slate-600">
          <li>
            Your email address comes from Supabase Auth and cannot be changed here.
          </li>
          <li>
            Your full name and role are stored in the <code>profiles</code> table.
          </li>
          <li>
            Role-based UI (admin vs user) is not built yet — everyone sees the same
            dashboard for now.
          </li>
        </ul>
      </section>
    </div>
  );
}
