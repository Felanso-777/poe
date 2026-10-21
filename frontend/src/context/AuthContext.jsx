import { createContext, useContext, useEffect, useState } from "react";
import { supabase } from "../lib/supabase";

const AuthContext = createContext(null);

/**
 * AuthProvider — manages Supabase authentication state.
 *
 * Exposes: user, role, fullName, loading, signIn, signUp, signOut
 *
 * Role and full name are read from the `profiles` table (linked to auth.users).
 * New signups get role = 'user' via the database trigger.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [role, setRole] = useState("user");
  const [fullName, setFullName] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    const loadUser = async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (mounted) {
        setUser(user);
        if (user) {
          await fetchProfile(user.id);
        }
        setLoading(false);
      }
    };

    loadUser();

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (_event, session) => {
        if (!mounted) return;
        const newUser = session?.user ?? null;
        setUser(newUser);
        if (newUser) {
          await fetchProfile(newUser.id);
        } else {
          setRole("user");
          setFullName("");
        }
        setLoading(false);
      },
    );

    return () => {
      mounted = false;
      if (subscription) {
        supabase.auth.removeSubscription(subscription.id);
      }
    };
  }, []);

  const fetchProfile = async (userId) => {
    try {
      const { data, error } = await supabase
        .from("profiles")
        .select("role, full_name, created_at")
        .eq("id", userId)
        .single();
      if (!error && data) {
        setRole(data.role || "user");
        setFullName(data.full_name || "");
      }
    } catch (err) {
      console.error("Failed to fetch profile:", err);
    }
  };

  const signIn = async (email, password) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    return { error };
  };

  const signUp = async (email, password, fullName) => {
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { full_name: fullName } },
    });
    return { error };
  };

  const signOut = async () => {
    const { error } = await supabase.auth.signOut();
    return { error };
  };

  return (
    <AuthContext.Provider value={{ user, role, fullName, loading, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
