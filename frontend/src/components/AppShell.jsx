import { NavLink, Outlet } from "react-router-dom";
import Navbar from "./Navbar";

const Icon = ({ d }) => (
  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
);

const navigation = [
  { to: "/", label: "Overview", end: true, d: "M3 11l9-8 9 8M5 10v10h14V10" },
  { to: "/history", label: "Session history", d: "M4 6h16M4 12h16M4 18h10" },
  { to: "/verify", label: "Verify a session", d: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM8.5 12l2.5 2.5 4.5-5" },
];

export default function AppShell() {
  return (
    <div className="min-h-screen">
      <Navbar />
      <div className="mx-auto flex max-w-[1440px]">
        <aside className="hidden w-60 shrink-0 px-4 py-8 lg:block">
          <nav aria-label="Primary navigation" className="space-y-1">
            {navigation.map((item) => (
              <NavItem key={item.to} item={item} />
            ))}
          </nav>
          <p className="mt-10 border-t border-slate-200 px-3 pt-5 text-xs leading-5 text-slate-500">
            Only session identifiers and Merkle roots are anchored on-chain. Raw activity data never leaves your machine.
          </p>
        </aside>
        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
          <nav aria-label="Primary navigation" className="mb-6 flex gap-2 overflow-x-auto lg:hidden">
            {navigation.map((item) => (
              <NavItem key={item.to} item={item} compact />
            ))}
          </nav>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function NavItem({ item, compact = false }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) =>
        `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${compact ? "whitespace-nowrap border" : ""} ${
          isActive ? "border-ink bg-ink text-white" : "border-slate-200 text-slate-600 hover:bg-white hover:text-ink lg:border-transparent"
        }`
      }
    >
      <Icon d={item.d} />
      {item.label}
    </NavLink>
  );
}
