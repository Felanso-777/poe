import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { BlockchainProvider } from "./context/BlockchainContext";
import Overview from "./pages/Overview";
import SessionHistoryPage from "./pages/SessionHistory";
import SessionDetails from "./pages/SessionDetails";
import Verify from "./pages/Verify";
import AppShell from "./components/AppShell";
import Login from "./pages/Login";         
import Register from "./pages/Register";

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: "/", element: <Overview /> },
      { path: "/history", element: <SessionHistoryPage /> },
      { path: "/sessions/:id", element: <SessionDetails /> },
      { path: "/verify", element: <Verify /> },
    ],
  },
  {
    path: "/login",
    element: <Login />,
  },
  {
    path: "/register",
    element: <Register />,
  },
]);


export default function App() {
  return (
    <BlockchainProvider>
      <RouterProvider router={router} />
    </BlockchainProvider>
  );
}
