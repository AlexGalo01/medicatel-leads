import { Briefcase, ListChecks, LogOut, Search, UserCog } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import { Button } from "./components/ui/button";

export function AppLayout(): JSX.Element {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="app-shell app-shell--with-sidebar">
      <aside className="app-sidebar" aria-label="Navegación principal">
        <div className="app-sidebar-brand ui-card">
          <span className="app-sidebar-brand-badge" aria-hidden>
            M
          </span>
          <div className="app-sidebar-brand-copy">
            <strong>Medicatel CRM</strong>
            <span>Lead Finder</span>
          </div>
        </div>

        <nav className="app-sidebar-nav">
          <NavLink to="/search" className={({ isActive }) => `app-sidebar-link ui-nav-link${isActive ? " is-active" : ""}`}>
            <Search size={16} aria-hidden />
            <span>Search</span>
          </NavLink>
          <NavLink to="/busquedas" className={({ isActive }) => `app-sidebar-link ui-nav-link${isActive ? " is-active" : ""}`}>
            <ListChecks size={16} aria-hidden />
            <span>Búsquedas</span>
          </NavLink>
          <NavLink to="/opportunities" className={({ isActive }) => `app-sidebar-link ui-nav-link${isActive ? " is-active" : ""}`}>
            <Briefcase size={16} aria-hidden />
            <span>Oportunidades</span>
          </NavLink>
          {user?.role === "admin" ? (
            <NavLink
              to="/admin/users"
              className={({ isActive }) => `app-sidebar-link ui-nav-link${isActive ? " is-active" : ""}`}
            >
              <UserCog size={16} aria-hidden />
              <span>Usuarios</span>
            </NavLink>
          ) : null}
        </nav>
        <div className="app-sidebar-user" aria-label="Usuario actual">
          <span className="app-sidebar-user-name" title={user?.email ?? ""}>
            {user?.display_name ?? "—"}
          </span>
          <Button
            type="button"
            variant="outline"
            className="workspace-tool-btn app-sidebar-logout"
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
          >
            <LogOut size={14} aria-hidden />
            Cerrar sesión
          </Button>
        </div>
      </aside>

      <main className="app-main app-main--with-sidebar">
        <Outlet />
      </main>
    </div>
  );
}

