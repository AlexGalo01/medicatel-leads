import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ChevronLeft,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  Power,
  X,
  Check,
} from "lucide-react";

import {
  deleteAdminUser,
  listAdminUsers,
  updateAdminUser,
} from "../api";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Select } from "../components/ui/select";
import { useAuth } from "../auth/AuthContext";
import type { Permission, UserPublic } from "../types";

const ALL_PERMISSIONS: { key: Permission; label: string }[] = [
  { key: "use_search", label: "Buscar leads" },
  { key: "manage_opportunities", label: "Gestionar oportunidades" },
];

/* ------------------------------------------------------------------ */
/*  Inline edit row                                                    */
/* ------------------------------------------------------------------ */

function UserEditRow({
  u,
  currentUserId,
  onClose,
}: {
  u: UserPublic;
  currentUserId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [displayName, setDisplayName] = useState(u.display_name);
  const [email, setEmail] = useState(u.email);
  const [role, setRole] = useState<"user" | "admin">(u.role);
  const [perms, setPerms] = useState<Permission[]>(u.permissions ?? []);
  const [err, setErr] = useState<string | null>(null);

  const togglePerm = (p: Permission) =>
    setPerms((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p],
    );

  const saveMut = useMutation({
    mutationFn: () =>
      updateAdminUser(u.user_id, {
        email,
        display_name: displayName,
        role,
        permissions: perms,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      onClose();
    },
    onError: (e: Error) => setErr(e.message),
  });

  const toggleActiveMut = useMutation({
    mutationFn: () =>
      updateAdminUser(u.user_id, { is_active: !u.is_active }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: (e: Error) => setErr(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteAdminUser(u.user_id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      onClose();
    },
    onError: (e: Error) => setErr(e.message),
  });

  const [confirmDelete, setConfirmDelete] = useState(false);
  const isSelf = u.user_id === currentUserId;

  return (
    <li className="admin-user-row admin-user-row--editing">
      <div className="admin-edit-grid">
        <label className="admin-field">
          <span className="admin-field-label">Nombre</span>
          <Input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </label>
        <label className="admin-field">
          <span className="admin-field-label">Correo</span>
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="admin-field">
          <span className="admin-field-label">Rol</span>
          <Select
            value={role}
            onChange={(e) => setRole(e.target.value as "user" | "admin")}
          >
            <option value="user">Usuario</option>
            <option value="admin">Administrador</option>
          </Select>
        </label>
        <fieldset className="admin-permissions-fieldset">
          <legend>Permisos</legend>
          {ALL_PERMISSIONS.map(({ key, label }) => (
            <label key={key} className="admin-perm-checkbox">
              <input
                type="checkbox"
                checked={role === "admin" || perms.includes(key)}
                disabled={role === "admin"}
                onChange={() => togglePerm(key)}
              />
              {label}
            </label>
          ))}
        </fieldset>
      </div>
      {err ? <p className="error-text">{err}</p> : null}
      <div className="admin-edit-actions">
        <Button
          className="cta-button"
          disabled={saveMut.isPending}
          onClick={() => saveMut.mutate()}
        >
          {saveMut.isPending ? (
            <Loader2 className="spin" size={14} aria-hidden />
          ) : (
            <Check size={14} aria-hidden />
          )}
          Guardar
        </Button>
        {!isSelf && (
          <Button
            className="link-button"
            disabled={toggleActiveMut.isPending}
            onClick={() => toggleActiveMut.mutate()}
          >
            <Power size={14} aria-hidden />
            {u.is_active ? "Desactivar" : "Activar"}
          </Button>
        )}
        {!isSelf &&
          (confirmDelete ? (
            <Button
              className="link-button danger-text"
              disabled={deleteMut.isPending}
              onClick={() => deleteMut.mutate()}
            >
              {deleteMut.isPending ? (
                <Loader2 className="spin" size={14} aria-hidden />
              ) : null}
              Confirmar eliminar
            </Button>
          ) : (
            <Button
              className="link-button danger-text"
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2 size={14} aria-hidden /> Eliminar
            </Button>
          ))}
        <Button className="link-button" onClick={onClose}>
          <X size={14} aria-hidden /> Cancelar
        </Button>
      </div>
    </li>
  );
}

/* ------------------------------------------------------------------ */
/*  Main page — solo listado                                           */
/* ------------------------------------------------------------------ */

export function AdminUsersPage(): JSX.Element {
  const { user } = useAuth();
  const [editingId, setEditingId] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["admin", "users"],
    queryFn: listAdminUsers,
    enabled: user?.role === "admin",
  });

  if (user?.role !== "admin") {
    return (
      <section className="panel error-text" style={{ padding: "2rem" }}>
        No autorizado. <Link to="/directories">Volver</Link>
      </section>
    );
  }

  return (
    <div className="admin-page">
      <nav className="admin-page-nav">
        <Link to="/directories" className="link-button">
          <ChevronLeft size={14} aria-hidden />
          Volver
        </Link>
      </nav>

      <div className="admin-page-head">
        <div>
          <h1 className="admin-page-title">Cuentas registradas</h1>
          <p className="muted-text" style={{ marginBottom: 0 }}>
            Listado de cuentas activas con sus roles y permisos.
          </p>
        </div>
        <Link to="/admin/users/new" className="cta-button">
          <Plus size={16} aria-hidden />
          Crear usuario
        </Link>
      </div>

      <Card className="panel admin-section-card" style={{ marginTop: "1.5rem" }}>
        {listQuery.isLoading ? (
          <p className="muted-text">Cargando…</p>
        ) : null}
        {listQuery.isError ? (
          <p className="error-text">No se pudo cargar el listado.</p>
        ) : null}
        {listQuery.data ? (
          <ul className="admin-users-list">
            {listQuery.data.items.map((u) =>
              editingId === u.user_id ? (
                <UserEditRow
                  key={u.user_id}
                  u={u}
                  currentUserId={user.user_id}
                  onClose={() => setEditingId(null)}
                />
              ) : (
                <li key={u.user_id} className="admin-user-row">
                  <div className="admin-user-info">
                    <strong>{u.display_name}</strong>
                    <span className="muted-text">{u.email}</span>
                  </div>
                  <div className="admin-user-badges">
                    <span className="admin-badge admin-badge--role">
                      {u.role === "admin" ? "Admin" : "Usuario"}
                    </span>
                    {!u.is_active && (
                      <span className="admin-badge admin-badge--inactive">
                        Inactivo
                      </span>
                    )}
                    {(u.permissions ?? []).map((p) => (
                      <span key={p} className="admin-badge admin-badge--perm">
                        {p === "use_search"
                          ? "Buscar"
                          : p === "manage_opportunities"
                            ? "Oportunidades"
                            : p}
                      </span>
                    ))}
                  </div>
                  <Button
                    className="link-button"
                    onClick={() => setEditingId(u.user_id)}
                  >
                    <Pencil size={14} aria-hidden /> Editar
                  </Button>
                </li>
              ),
            )}
          </ul>
        ) : null}
      </Card>
    </div>
  );
}
