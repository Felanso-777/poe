import { createBrowserRouter, RouterProvider, Navigate } from "react-router-dom";
import { BlockchainProvider } from "./context/BlockchainContext";
import { AuthProvider, useAuth } from "./context/AuthContext";
import AppShell from "./components/AppShell";
import Overview from "./pages/Overview";
import SessionHistoryPage from "./pages/SessionHistory";
import SessionDetails from "./pages/SessionDetails";
import Verify from "./pages/Verify";
import Profile from "./pages/Profile";
import Login from "./pages/Login";
import Register from "./pages/Register";

/**
 * ProtectedRoute — requires authentication.
 * Redirects to /login if not logged in.
 */
function ProtectedRoute({ element }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return element;
}

/**
 * GuestRoute — only for unauthenticated users.
 * Redirects to / if already logged in.
 */
function GuestRoute({ element }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user) return <Navigate to="/" replace />;
  return element;
}

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: "/", element: <ProtectedRoute element={<Overview />} /> },
      { path: "/history", element: <ProtectedRoute element={<SessionHistoryPage />} /> },
      { path: "/sessions/:id", element: <ProtectedRoute element={<SessionDetails />} /> },
      { path: "/verify", element: <ProtectedRoute element={<Verify />} /> },
      { path: "/profile", element: <ProtectedRoute element={<Profile />} /> },
    ],
  },
  {
    path: "/login",
    element: <GuestRoute element={<Login />} />,
  },
  {
    path: "/register",
    element: <GuestRoute element={<Register />} />,
  },
]);

export default function App() {
  return (
    <AuthProvider>
      <BlockchainProvider>
        <RouterProvider router={router} />
      </BlockchainProvider>
    </AuthProvider>
  );
}
