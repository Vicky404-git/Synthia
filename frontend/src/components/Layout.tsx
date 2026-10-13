import { NavLink, Outlet } from "react-router-dom";
import { useBackend } from "../state/BackendContext";
import { useHistory } from "../state/HistoryContext";

const NAV = [
  { to: "/", label: "Assistant", glyph: "▌", end: true },
  { to: "/history", label: "History", glyph: "≡", end: false },
  { to: "/resources", label: "Cloud", glyph: "☁", end: false },
  { to: "/settings", label: "Settings", glyph: "⚙", end: false },
];

function NavItems({ mobile = false }: { mobile?: boolean }) {
  return (
    <>
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            `nav-link ${isActive ? "active" : ""}`
          }
        >
          <span className="glyph" aria-hidden="true">
            {item.glyph}
          </span>
          <span>{item.label}</span>
        </NavLink>
      ))}
      {mobile && null}
    </>
  );
}

export function Layout() {
  const { ready, error, loading } = useBackend();
  const { events } = useHistory();
  const failures = events.filter(
    (event) => event.status !== "success" && event.status !== "tool_succeeded",
  ).length;

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

      <div className="body">
        <nav className="sidebar" aria-label="Main navigation">
          <NavItems />
          <div className="sidebar-footer">
            <div>{events.length} history events</div>
            <div>{failures} failed</div>
            <div style={{ marginTop: 6 }}>local to this browser</div>
          </div>
        </nav>

        <main className="content">
          <Outlet />
        </main>
      </div>

      <nav className="bottomnav" aria-label="Main navigation">
        <NavItems mobile />
      </nav>
    </div>
  );
}
