import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  Loader2,
  Pencil,
  Plus,
  Shield,
  Trash2,
  UserCheck,
  Users,
  X,
} from "lucide-react";

import { createAdminUser, deleteAdminUser, listAdminUsers, updateAdminUser } from "../api";
import { useAuth } from "../auth/AuthContext";
import type { Permission, UserPublic, UserRole } from "../types";

// ── Avatar helpers ──────────────────────────────────────────────────────────
const AVATAR_PALETTE = [
  { bg: "#DBEAFE", color: "#1D4ED8" },
  { bg: "#FEF3C7", color: "#D97706" },
  { bg: "#D1FAE5", color: "#059669" },
  { bg: "#EDE9FE", color: "#7C3AED" },
  { bg: "#FCE7F3", color: "#DB2777" },
  { bg: "#FEE2E2", color: "#DC2626" },
];
function getAvatarStyle(name: string) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = ((h << 5) - h + name.charCodeAt(i)) | 0;
  return AVATAR_PALETTE[Math.abs(h) % AVATAR_PALETTE.length];
}
function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

// ── Permissions ─────────────────────────────────────────────────────────────
const ALL_PERMISSIONS: { key: Permission; label: string; desc: string }[] = [
  { key: "use_search", label: "Búsqueda de leads", desc: "Permite buscar y filtrar la base de datos" },
  { key: "manage_opportunities", label: "Gestionar oportunidades", desc: "Permite mover leads en el Kanban" },
];

// ── Panel state ──────────────────────────────────────────────────────────────
interface PanelUser {
  mode: "create" | "edit";
  user?: UserPublic;
}

// ── Slide Panel ──────────────────────────────────────────────────────────────
function UserPanel({
  panel,
  onClose,
}: {
  panel: PanelUser;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const isEdit = panel.mode === "edit" && panel.user != null;
  const u = panel.user;

  const [displayName, setDisplayName] = useState(u?.display_name ?? "");
  const [email, setEmail] = useState(u?.email ?? "");
  const [role, setRole] = useState<UserRole>(u?.role ?? "user");
  const [perms, setPerms] = useState<Permission[]>(u?.permissions ?? []);
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const togglePerm = (p: Permission) =>
    setPerms((prev) => prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]);

  const saveMut = useMutation({
    mutationFn: () =>
      isEdit
        ? updateAdminUser(u!.user_id, {
            email,
            display_name: displayName,
            role,
            permissions: perms,
            ...(password ? { password } : {}),
          } as any)
        : createAdminUser({
            email,
            display_name: displayName,
            role,
            permissions: perms,
            password,
          }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      onClose();
    },
    onError: (e: Error) => setErr(e.message),
  });

  const isAdminRole = role === "admin";

  return (
    <>
      {/* Overlay */}
      <div
        style={{
          position: "fixed", inset: 0, background: "rgba(17,24,39,0.5)",
          zIndex: 40,
        }}
        onClick={onClose}
      />
      {/* Panel */}
      <aside style={{
        position: "fixed", top: 0, right: 0, height: "100%",
        width: 380, background: "white", zIndex: 50,
        display: "flex", flexDirection: "column",
        borderLeft: "1px solid #E5E7EB",
        boxShadow: "-4px 0 15px -3px rgba(0,0,0,0.1)",
        animation: "slideInRight 200ms ease-out",
      }}>
        {/* Header */}
        <div style={{
          padding: "20px 24px", borderBottom: "1px solid #E5E7EB",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          background: "#F8FAFC", flexShrink: 0,
        }}>
          <h2 style={{ margin: 0, fontSize: 17, fontWeight: 600, color: "#111827" }}>
            {isEdit ? "Editar Usuario" : "Invitar Usuario"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: "4px 6px", border: "none", background: "none",
              cursor: "pointer", color: "#9CA3AF", borderRadius: 6,
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: "auto", padding: 24 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <span style={{ fontSize: 13, fontWeight: 500, color: "#374151" }}>Nombre completo</span>
              <input
                className="ui-input"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Ej. Juan Pérez"
              />
            </label>

            <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <span style={{ fontSize: 13, fontWeight: 500, color: "#374151" }}>Email</span>
              <input
                className="ui-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="juan@empresa.com"
              />
            </label>

            <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <span style={{ fontSize: 13, fontWeight: 500, color: "#374151" }}>Rol</span>
              <select
                className="ui-input"
                value={role}
                onChange={(e) => setRole(e.target.value as UserRole)}
                style={{ background: "white" }}
              >
                <option value="user">Usuario</option>
                <option value="admin">Administrador</option>
              </select>
            </label>

            <div style={{ opacity: isAdminRole ? 0.5 : 1 }}>
              <p style={{ fontSize: 13, fontWeight: 500, color: "#374151", margin: "0 0 8px" }}>
                Permisos específicos
              </p>
              <div style={{
                background: "#F9FAFB", border: "1px solid #E5E7EB",
                borderRadius: 8, padding: "14px 16px",
                display: "flex", flexDirection: "column", gap: 12,
              }}>
                {ALL_PERMISSIONS.map(({ key, label, desc }) => (
                  <label key={key} style={{ display: "flex", alignItems: "flex-start", gap: 10, cursor: isAdminRole ? "not-allowed" : "pointer" }}>
                    <input
                      type="checkbox"
                      checked={isAdminRole || perms.includes(key)}
                      disabled={isAdminRole}
                      onChange={() => togglePerm(key)}
                      style={{ marginTop: 2, width: 15, height: 15, accentColor: "#4F46E5" }}
                    />
                    <div>
                      <span style={{ display: "block", fontSize: 13, fontWeight: 500, color: "#111827" }}>{label}</span>
                      <span style={{ display: "block", fontSize: 11, color: "#6B7280" }}>{desc}</span>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div style={{ borderTop: "1px solid #E5E7EB", paddingTop: 16 }}>
              <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                <span style={{ fontSize: 13, fontWeight: 500, color: "#374151" }}>
                  {isEdit ? "Nueva contraseña (Opcional)" : "Contraseña"}
                </span>
                <input
                  className="ui-input"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={isEdit ? "Dejar en blanco para no cambiar" : "Contraseña de acceso"}
                />
              </label>
            </div>

            {err && <p style={{ margin: 0, fontSize: 13, color: "#DC2626" }}>{err}</p>}
          </div>
        </div>

        {/* Footer */}
        <div style={{
          padding: "16px 24px", borderTop: "1px solid #E5E7EB",
          background: "#F9FAFB", display: "flex", justifyContent: "flex-end", gap: 10, flexShrink: 0,
        }}>
          <button type="button" className="link-button" onClick={onClose}>Cancelar</button>
          <button
            type="button"
            className="cta-button"
            disabled={saveMut.isPending || !displayName.trim() || !email.trim() || (!isEdit && !password)}
            onClick={() => saveMut.mutate()}
          >
            {saveMut.isPending ? <Loader2 size={14} className="spin" aria-hidden /> : null}
            Guardar cambios
          </button>
        </div>
      </aside>
    </>
  );
}

// ── Delete Modal ─────────────────────────────────────────────────────────────
function DeleteModal({
  user,
  onClose,
}: {
  user: UserPublic;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [err, setErr] = useState<string | null>(null);

  const deleteMut = useMutation({
    mutationFn: () => deleteAdminUser(user.user_id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      onClose();
    },
    onError: (e: Error) => setErr(e.message),
  });

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(17,24,39,0.5)",
      zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
    }}>
      <div style={{
        background: "white", borderRadius: 12, padding: 24, maxWidth: 360, width: "100%",
        textAlign: "center", boxShadow: "0 20px 25px -5px rgba(0,0,0,0.1)",
      }}>
        <div style={{
          width: 48, height: 48, borderRadius: "50%",
          background: "#FEE2E2", color: "#DC2626",
          display: "flex", alignItems: "center", justifyContent: "center",
          margin: "0 auto 16px",
        }}>
          <AlertTriangle size={22} />
        </div>
        <h3 style={{ margin: "0 0 8px", fontSize: 16, fontWeight: 700, color: "#111827" }}>
          ¿Eliminar a {user.display_name}?
        </h3>
        <p style={{ margin: "0 0 24px", fontSize: 13, color: "#6B7280", lineHeight: 1.5 }}>
          Esta acción no se puede deshacer y el usuario perderá acceso inmediatamente.
        </p>
        {err && <p style={{ fontSize: 13, color: "#DC2626", marginBottom: 12 }}>{err}</p>}
        <div style={{ display: "flex", gap: 10 }}>
          <button type="button" className="link-button" style={{ flex: 1 }} onClick={onClose}>
            Cancelar
          </button>
          <button
            type="button"
            disabled={deleteMut.isPending}
            onClick={() => deleteMut.mutate()}
            style={{
              flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
              background: "#DC2626", color: "white", border: "none",
              padding: "8px 16px", borderRadius: 6, fontSize: 14, fontWeight: 500,
              cursor: deleteMut.isPending ? "not-allowed" : "pointer",
              opacity: deleteMut.isPending ? 0.7 : 1,
            }}
          >
            {deleteMut.isPending ? <Loader2 size={14} className="spin" aria-hidden /> : null}
            Eliminar
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Skeleton row ─────────────────────────────────────────────────────────────
function SkeletonRow() {
  return (
    <tr>
      <td style={{ padding: "16px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span className="skel" style={{ width: 32, height: 32, borderRadius: "50%", flexShrink: 0 }} />
          <div>
            <span className="skel" style={{ display: "block", width: 120, height: 13, marginBottom: 5 }} />
            <span className="skel" style={{ display: "block", width: 160, height: 11 }} />
          </div>
        </div>
      </td>
      <td style={{ padding: "16px 24px" }}><span className="skel" style={{ display: "block", width: 60, height: 20, borderRadius: 999 }} /></td>
      <td style={{ padding: "16px 24px" }}><span className="skel" style={{ display: "block", width: 80, height: 20, borderRadius: 4 }} /></td>
      <td style={{ padding: "16px 24px" }}><span className="skel" style={{ display: "block", width: 40, height: 20, borderRadius: 999 }} /></td>
      <td style={{ padding: "16px 24px" }}><span className="skel" style={{ display: "block", width: 80, height: 13 }} /></td>
      <td style={{ padding: "16px 24px" }} />
    </tr>
  );
}

// ── Toggle Switch ────────────────────────────────────────────────────────────
function ToggleSwitch({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={onChange}
      style={{
        width: 36, height: 20, borderRadius: 999,
        background: checked ? "#4F46E5" : "#D1D5DB",
        border: "none", cursor: disabled ? "not-allowed" : "pointer",
        position: "relative", transition: "background 0.2s",
        flexShrink: 0, padding: 0,
      }}
    >
      <span style={{
        position: "absolute", top: 2,
        left: checked ? 18 : 2,
        width: 16, height: 16, borderRadius: "50%",
        background: "white",
        boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
        transition: "left 0.2s",
      }} />
    </button>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export function AdminUsersPage(): JSX.Element {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [panel, setPanel] = useState<PanelUser | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<UserPublic | null>(null);

  const listQuery = useQuery({
    queryKey: ["admin", "users"],
    queryFn: listAdminUsers,
    enabled: user?.role === "admin",
  });

  const toggleActiveMut = useMutation({
    mutationFn: ({ userId, isActive }: { userId: string; isActive: boolean }) =>
      updateAdminUser(userId, { is_active: isActive }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  if (user?.role !== "admin") {
    return (
      <section style={{ padding: "2rem" }}>
        <p className="error-text">No autorizado.</p>
        <Link to="/lists">Volver</Link>
      </section>
    );
  }

  const users = listQuery.data?.items ?? [];
  const totalUsers = users.length;
  const totalAdmins = users.filter((u) => u.role === "admin").length;
  const totalActive = users.filter((u) => u.is_active).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden", background: "#F8FAFC" }}>

      {/* Header */}
      <header style={{
        background: "white", borderBottom: "1px solid #E5E7EB",
        padding: "20px 32px", display: "flex", alignItems: "center",
        justifyContent: "space-between", flexShrink: 0,
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#111827" }}>Usuarios</h1>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "#6B7280" }}>Gestiona los accesos al sistema</p>
        </div>
        <button
          type="button"
          className="cta-button"
          onClick={() => setPanel({ mode: "create" })}
          style={{ display: "flex", alignItems: "center", gap: 7 }}
        >
          <Plus size={15} aria-hidden /> Invitar usuario
        </button>
      </header>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: "auto", padding: 32 }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", display: "flex", flexDirection: "column", gap: 24 }}>

          {/* Stats */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 20 }}>
            {[
              { icon: <Users size={20} />, label: "Total usuarios", value: listQuery.isLoading ? "—" : totalUsers, bg: "#EFF6FF", color: "#2563EB" },
              { icon: <Shield size={20} />, label: "Admins", value: listQuery.isLoading ? "—" : totalAdmins, bg: "#EEF2FF", color: "#4F46E5" },
              { icon: <UserCheck size={20} />, label: "Usuarios activos", value: listQuery.isLoading ? "—" : totalActive, bg: "#F0FDF4", color: "#059669" },
            ].map(({ icon, label, value, bg, color }) => (
              <div key={label} style={{
                background: "white", borderRadius: 12, border: "1px solid #E5E7EB",
                padding: "20px 24px", display: "flex", alignItems: "center", gap: 16,
                boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
              }}>
                <div style={{
                  width: 44, height: 44, borderRadius: "50%",
                  background: bg, color, flexShrink: 0,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  {icon}
                </div>
                <div>
                  <p style={{ margin: 0, fontSize: 13, color: "#6B7280", fontWeight: 500 }}>{label}</p>
                  <p style={{ margin: "4px 0 0", fontSize: 24, fontWeight: 700, color: "#111827", lineHeight: 1 }}>
                    {value}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* Table */}
          <div style={{
            background: "white", borderRadius: 12, border: "1px solid #E5E7EB",
            boxShadow: "0 1px 3px rgba(0,0,0,0.06)", overflow: "hidden",
          }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ background: "#F8FAFC", borderBottom: "1px solid #E5E7EB" }}>
                    {["Usuario", "Rol", "Permisos", "Estado", "Última actividad", "Acciones"].map((h, i) => (
                      <th key={h} style={{
                        padding: "12px 24px", textAlign: i === 5 ? "right" : "left",
                        fontSize: 11, fontWeight: 600, color: "#6B7280",
                        textTransform: "uppercase", letterSpacing: "0.06em",
                        whiteSpace: "nowrap",
                      }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {listQuery.isLoading ? (
                    Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)
                  ) : listQuery.isError ? (
                    <tr>
                      <td colSpan={6} style={{ padding: "32px 24px", textAlign: "center", color: "#DC2626", fontSize: 13 }}>
                        No se pudo cargar el listado.
                      </td>
                    </tr>
                  ) : users.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ padding: "40px 24px", textAlign: "center", color: "#9CA3AF", fontSize: 13 }}>
                        Sin usuarios registrados.
                      </td>
                    </tr>
                  ) : (
                    users.map((u) => {
                      const av = getAvatarStyle(u.display_name);
                      const isSelf = u.user_id === user.user_id;
                      return (
                        <tr
                          key={u.user_id}
                          className="admin-user-table-row"
                          style={{ borderBottom: "1px solid #F3F4F6" }}
                        >
                          {/* Usuario */}
                          <td style={{ padding: "14px 24px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                              <div style={{
                                width: 32, height: 32, borderRadius: "50%", flexShrink: 0,
                                background: av.bg, color: av.color,
                                display: "flex", alignItems: "center", justifyContent: "center",
                                fontSize: 11, fontWeight: 600,
                              }}>
                                {initials(u.display_name)}
                              </div>
                              <div>
                                <p style={{ margin: 0, fontWeight: 600, color: "#111827" }}>{u.display_name}</p>
                                <p style={{ margin: 0, fontSize: 12, color: "#6B7280" }}>{u.email}</p>
                              </div>
                            </div>
                          </td>

                          {/* Rol */}
                          <td style={{ padding: "14px 24px" }}>
                            <span style={{
                              display: "inline-flex", alignItems: "center",
                              padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 500,
                              background: u.role === "admin" ? "#EEF2FF" : "#F3F4F6",
                              color: u.role === "admin" ? "#4338CA" : "#374151",
                            }}>
                              {u.role === "admin" ? "Admin" : "Usuario"}
                            </span>
                          </td>

                          {/* Permisos */}
                          <td style={{ padding: "14px 24px" }}>
                            {u.role === "admin" ? (
                              <span style={{ fontSize: 12, color: "#9CA3AF", fontStyle: "italic" }}>Acceso total</span>
                            ) : (
                              <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                                {(u.permissions ?? []).map((p) => (
                                  <span key={p} style={{
                                    display: "inline-flex", alignItems: "center",
                                    padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 500,
                                    background: p === "use_search" ? "#EEF2FF" : "#F0FDF4",
                                    color: p === "use_search" ? "#4F46E5" : "#059669",
                                  }}>
                                    {p === "use_search" ? "Búsqueda" : "Oportunidades"}
                                  </span>
                                ))}
                                {(u.permissions ?? []).length === 0 && (
                                  <span style={{ fontSize: 12, color: "#D1D5DB" }}>Sin permisos</span>
                                )}
                              </div>
                            )}
                          </td>

                          {/* Estado toggle */}
                          <td style={{ padding: "14px 24px" }}>
                            <ToggleSwitch
                              checked={u.is_active}
                              disabled={isSelf || toggleActiveMut.isPending}
                              onChange={() => toggleActiveMut.mutate({ userId: u.user_id, isActive: !u.is_active })}
                            />
                          </td>

                          {/* Última actividad */}
                          <td style={{ padding: "14px 24px", color: "#6B7280", fontSize: 13 }}>—</td>

                          {/* Acciones */}
                          <td style={{ padding: "14px 24px", textAlign: "right" }}>
                            <div className="admin-user-actions" style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4 }}>
                              <button
                                type="button"
                                title="Editar"
                                onClick={() => setPanel({ mode: "edit", user: u })}
                                style={{
                                  padding: "6px 7px", border: "none", background: "none",
                                  cursor: "pointer", color: "#9CA3AF", borderRadius: 6,
                                  transition: "color 0.15s, background 0.15s",
                                }}
                                onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = "#4F46E5"; (e.currentTarget as HTMLButtonElement).style.background = "#EEF2FF"; }}
                                onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = "#9CA3AF"; (e.currentTarget as HTMLButtonElement).style.background = "none"; }}
                              >
                                <Pencil size={14} />
                              </button>
                              {!isSelf && (
                                <button
                                  type="button"
                                  title="Eliminar"
                                  onClick={() => setDeleteTarget(u)}
                                  style={{
                                    padding: "6px 7px", border: "none", background: "none",
                                    cursor: "pointer", color: "#9CA3AF", borderRadius: 6,
                                    transition: "color 0.15s, background 0.15s",
                                  }}
                                  onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = "#DC2626"; (e.currentTarget as HTMLButtonElement).style.background = "#FEE2E2"; }}
                                  onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = "#9CA3AF"; (e.currentTarget as HTMLButtonElement).style.background = "none"; }}
                                >
                                  <Trash2 size={14} />
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {/* Slide Panel */}
      {panel && <UserPanel panel={panel} onClose={() => setPanel(null)} />}

      {/* Delete Modal */}
      {deleteTarget && (
        <DeleteModal user={deleteTarget} onClose={() => setDeleteTarget(null)} />
      )}
    </div>
  );
}
