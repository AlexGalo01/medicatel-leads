import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ChevronLeft, Loader2 } from "lucide-react";

import { createAdminUser } from "../api";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Select } from "../components/ui/select";
import { useAuth } from "../auth/AuthContext";
import type { Permission } from "../types";

const ALL_PERMISSIONS: { key: Permission; label: string }[] = [
  { key: "use_search", label: "Buscar leads" },
  { key: "manage_opportunities", label: "Gestionar oportunidades" },
];

export function AdminCreateUserPage(): JSX.Element {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<"user" | "admin">("user");
  const [perms, setPerms] = useState<Permission[]>([]);
  const [formErr, setFormErr] = useState<string | null>(null);

  const togglePerm = (p: Permission) =>
    setPerms((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p],
    );

  const createMut = useMutation({
    mutationFn: createAdminUser,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      navigate("/admin/users");
    },
    onError: (e: Error) => setFormErr(e.message),
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
        <Link to="/admin/users" className="link-button">
          <ChevronLeft size={14} aria-hidden />
          Volver al listado
        </Link>
      </nav>

      <h1 className="admin-page-title">Nuevo usuario</h1>
      <p className="muted-text" style={{ marginBottom: "1.5rem" }}>
        Crea una cuenta nueva con rol y permisos específicos.
      </p>

      <Card className="panel admin-section-card">
        <form
          className="admin-create-form"
          onSubmit={(e) => {
            e.preventDefault();
            setFormErr(null);
            createMut.mutate({
              email,
              password,
              display_name: displayName,
              role,
              permissions: perms,
            });
          }}
        >
          <div className="admin-form-row">
            <label className="admin-field">
              <span className="admin-field-label">Correo</span>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </label>
            <label className="admin-field">
              <span className="admin-field-label">Contraseña (mín. 8)</span>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={8}
                required
              />
            </label>
          </div>
          <div className="admin-form-row">
            <label className="admin-field">
              <span className="admin-field-label">Nombre visible</span>
              <Input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                required
              />
            </label>
            <label className="admin-field">
              <span className="admin-field-label">Rol</span>
              <Select
                value={role}
                onChange={(e) => setRole(e.target.value as "user" | "admin")}
                required
              >
                <option value="user">Usuario</option>
                <option value="admin">Administrador</option>
              </Select>
            </label>
          </div>

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
            {role === "admin" && (
              <p className="muted-text" style={{ margin: "0.25rem 0 0", fontSize: 12 }}>
                Los administradores tienen todos los permisos.
              </p>
            )}
          </fieldset>

          {formErr ? <p className="error-text">{formErr}</p> : null}

          <div style={{ display: "flex", gap: "0.75rem", alignSelf: "flex-start" }}>
            <Link to="/admin/users" className="link-button">
              Cancelar
            </Link>
            <Button type="submit" className="cta-button" disabled={createMut.isPending}>
              {createMut.isPending ? (
                <Loader2 className="spin" size={16} aria-hidden />
              ) : null}
              Crear usuario
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
