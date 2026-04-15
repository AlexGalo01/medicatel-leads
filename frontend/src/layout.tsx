import { Link, Outlet } from "react-router-dom";

export function AppLayout(): JSX.Element {
  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Medicatel Lead Engine</h1>
        <nav className="nav-links">
          <Link to="/search">Nueva búsqueda</Link>
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}

