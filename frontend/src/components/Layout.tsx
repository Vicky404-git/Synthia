import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useBackend } from "../state/BackendContext";
import { useHistory } from "../state/HistoryContext";
import {
  CloudIcon,
  ConsoleIcon,
  HistoryIcon,
  SlidersIcon,
} from "./icons";

const NAV = [
  { to: "/", label: "Assistant", Icon: ConsoleIcon, end: true },
  { to: "/history", label: "History", Icon: HistoryIcon, end: false },
  { to: "/resources", label: "Cloud", Icon: CloudIcon, end: false },
  { to: "/settings", label: "Settings", Icon: SlidersIcon, end: false },
];

function NavItems() {
  return (
    <>
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
        >
          <span className="glyph" aria-hidden="true">
            <item.Icon size={16} />
          </span>
          <span>{item.label}</span>
        </NavLink>
      ))}
    </>
  );
}

/**
 * A small, always-visible system readout under the title bar. It only shows
 * values the app actually knows (release, environment, link state, history
 * size and a live clock) — it is not a fake HUD.
 */
function StatusStrip() {
  const { ready, error, loading } = useBackend();
  const { events } = useHistory();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const link = error ? "offline" : loading ? "connecting" : "ready";
  const failures = events.filter(
    (event) => event.status !== "success" && event.status !== "tool_succeeded",
  ).length;

  return (
    <div className="status-strip" role="status" aria-label="System status">
      <span className="status-item">
        <span className="key">SYS</span>
        <span className="val">{ready?.version ?? "—"}</span>
      </span>
      <span className="strip-sep" aria-hidden="true">
        /
      </span>
      <span className="status-item">
        <span className="key">ENV</span>
        <span className="val">{ready?.environment ?? "—"}</span>
      </span>
      <span className="strip-sep" aria-hidden="true">
        /
      </span>
      <span className="status-item">
        <span className="key">LINK</span>
        <span className={`val ${link === "ready" ? "on" : "off"}`}>{link}</span>
      </span>
      <span className="strip-sep" aria-hidden="true">
        /
      </span>
      <span className="status-item">
        <span className="key">LOG</span>
        <span className="val">
          {events.length} events{failures ? ` · ${failures} failed` : ""}
        </span>
      </span>
      <span className="strip-spacer" />
      <span className="strip-clock">{now.toLocaleTimeString()}</span>
    </div>
  );
}

export function Layout() {
  const { ready, error, loading } = useBackend();

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">S</div>
          <div style={{ minWidth: 0 }}>
            <div className="brand-name">synthia</div>
            <div className="brand-tag">speak to your infrastructure</div>
          </div>
        </div>
        <div className="topbar-right">
          {ready?.demo_mode && <span className="pill demo">demo mode</span>}
          {error ? (
            <span className="pill error">
              <span className="dot" aria-hidden="true" />
              backend offline
            </span>
          ) : loading ? (
            <span className="pill neutral">
              <span className="dot" aria-hidden="true" />
              connecting…
            </span>
          ) : (
            <span className="pill success">
              <span className="dot" aria-hidden="true" />
              backend ready
            </span>
          )}
        </div>
      </header>

      <StatusStrip />

      <div className="body">
        <nav className="sidebar" aria-label="Main navigation">
          <NavItems />
          <div className="sidebar-footer">
            <div>history stored locally</div>
            <div>in this browser only</div>
          </div>
        </nav>

        <main className="content">
          <Outlet />
        </main>
      </div>

      <nav className="bottomnav" aria-label="Main navigation">
        <NavItems />
      </nav>
    </div>
  );
}
