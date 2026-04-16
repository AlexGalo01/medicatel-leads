import { Link, Outlet } from "react-router-dom";
import logoImage from "./assets/Logo.png";

export function AppLayout(): JSX.Element {
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/search" className="brand-link">
          <img src={logoImage} alt="MedicatelCRM" className="brand-logo" />
          <h1>MedicatelCRM</h1>
        </Link>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}

