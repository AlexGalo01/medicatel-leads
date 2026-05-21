import { Bot, FolderKanban, LogOut, Search, UserCog, Globe } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import { usePermissions } from "./auth/usePermissions";
import { Button } from "./components/ui/button";

const AVATAR_PALETTE = [
  { bg: "#EEF2FF", color: "#4338CA" },
  { bg: "#F0FDF4", color: "#166534" },
  { bg: "#FFF7ED", color: "#9A3412" },
  { bg: "#FDF4FF", color: "#7E22CE" },
  { bg: "#F0F9FF", color: "#0369A1" },
  { bg: "#FFF1F2", color: "#9F1239" },
];

function getAvatarStyle(text: string) {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[h % AVATAR_PALETTE.length];
}

function initials(text: string): string {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

export function AppLayout(): JSX.Element {
  const { user, logout } = useAuth();
  const { canSearch, isAdmin } = usePermissions();
  const navigate = useNavigate();

  const avatarStyle = getAvatarStyle(user?.display_name || "?");
  const userInitials = initials(user?.display_name || "?");
  const roleLabel = user?.role === "admin" ? "Admin" : "Usuario";

  return (
    <div className="app-shell app-shell--with-sidebar">
      <aside className="app-sidebar" aria-label="Navegación principal">
        {/* Brand */}
        <div className="app-sidebar-brand">
          <div className="app-sidebar-brand-icon">
            <Bot size={24} color="#0000FF" />
          </div>
          <div className="app-sidebar-brand-copy">
            <strong>LeadGen AI</strong>
            <span>Lead Finder</span>
          </div>
        </div>

        {/* Nav */}
        <nav className="app-sidebar-nav">
          {canSearch && (
            <NavLink to="/search" className={({ isActive }) => `app-sidebar-link ui-nav-link${isActive ? " is-active" : ""}`}>
              <Search size={16} aria-hidden />
              <span>Search</span>
            </NavLink>
          )}
          <NavLink to="/lists" className={({ isActive }) => `app-sidebar-link ui-nav-link${isActive ? " is-active" : ""}`}>
            <FolderKanban size={16} aria-hidden />
            <span>Listas</span>
          </NavLink>
          {canSearch && (
            <NavLink to="/sources" className={({ isActive }) => `app-sidebar-link ui-nav-link${isActive ? " is-active" : ""}`}>
              <Globe size={16} aria-hidden />
              <span>Fuentes</span>
            </NavLink>
          )}
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

        {/* User */}
        <div className="app-sidebar-user" aria-label="Usuario actual">
          <div className="app-sidebar-user-row">
            <div className="app-sidebar-user-avatar" style={{ background: avatarStyle.bg, color: avatarStyle.color }}>
              {userInitials}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="app-sidebar-user-name" title={user?.email ?? ""}>
                {user?.display_name ?? "—"}
              </div>
              <div className="app-sidebar-user-role">{roleLabel}</div>
            </div>
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
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
        </div>
      </aside>

      <main className="app-main app-main--with-sidebar">
        <Outlet />
      </main>
    </div>
  );
}
