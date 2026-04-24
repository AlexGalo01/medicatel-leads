import { Briefcase, FolderKanban, LogOut, Search, UserCog } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import { usePermissions } from "./auth/usePermissions";
import { Button } from "./components/ui/button";

export function AppLayout(): JSX.Element {
  const { user, logout } = useAuth();
  const { canSearch, isAdmin } = usePermissions();
  const navigate = useNavigate();

  return (
    <div className="app-shell app-shell--with-sidebar">
      <aside className="app-sidebar" aria-label="Navegación principal">
        <div className="app-sidebar-brand ui-card">
          <span className="app-sidebar-brand-badge" aria-hidden>
            AI
          </span>
          <div className="app-sidebar-brand-copy">
            <strong>AI CRM</strong>
          </div>
        </div>

        <nav className="app-sidebar-nav">
          {canSearch && (
            <NavLink to="/search" className={({ isActive }) => `app-sidebar-link ui-nav-link${isActive ? " is-active" : ""}`}>
              <Search size={16} aria-hidden />
              <span>Search</span>
            </NavLink>
          )}
          <NavLink to="/directories" className={({ isActive }) => `app-sidebar-link ui-nav-link${isActive ? " is-active" : ""}`}>
            <FolderKanban size={16} aria-hidden />
            <span>Directorios</span>
          </NavLink>
          <NavLink to="/opportunities" className={({ isActive }) => `app-sidebar-link ui-nav-link${isActive ? " is-active" : ""}`}>
            <Briefcase size={16} aria-hidden />
            <span>Oportunidades</span>
          </NavLink>
          {isAdmin && (
            <NavLink
              to="/admin/users"
              className={({ isActive }) => `app-sidebar-link ui-nav-link${isActive ? " is-active" : ""}`}
            >
              <UserCog size={16} aria-hidden />
              <span>Usuarios</span>
            </NavLink>
          )}
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

