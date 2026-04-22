import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ChevronLeft, Loader2 } from "lucide-react";

import { createAdminUser, listAdminUsers } from "../api";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Select } from "../components/ui/select";
import { useAuth } from "../auth/AuthContext";

export function AdminUsersPage(): JSX.Element {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<"user" | "admin">("user");
  const [formErr, setFormErr] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["admin", "users"],
    queryFn: listAdminUsers,
    enabled: user?.role === "admin",
  });

  const createMut = useMutation({
    mutationFn: createAdminUser,
    onSuccess: () => {
      setEmail("");
      setPassword("");
      setDisplayName("");
      setRole("user");
      setFormErr(null);
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: (e: Error) => setFormErr(e.message),
  });

  if (user?.role !== "admin") {
    return (
      <section className="panel error-text">
        No autorizado. <Link to="/opportunities">Volver</Link>
      </section>
    );
  }

  return (
    <div className="opportunity-ficha-page">
      <nav className="opportunity-detail-nav" aria-label="Navegación">
        <Link to="/opportunities" className="link-button">
          <ChevronLeft size={14} aria-hidden />
          Volver
        </Link>
      </nav>
      <Card className="panel opportunity-card">
        <h1 className="opportunity-journey-heading">Usuarios</h1>
        <p className="muted-text">Solo administradores pueden crear cuentas.</p>

        <h2 className="opportunity-card-subtitle" style={{ marginTop: "1.25rem" }}>
          Nuevo usuario
        </h2>
        <form
          className="admin-user-form"
          onSubmit={(e) => {
            e.preventDefault();
            setFormErr(null);
            createMut.mutate({ email, password, display_name: displayName, role });
          }}
        >
          <label className="opportunity-field">
            <span>Correo</span>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label className="opportunity-field">
            <span>Contraseña (mín. 8)</span>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={8}
              required
            />
          </label>
          <label className="opportunity-field">
            <span>Nombre visible</span>
            <Input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              required
            />
          </label>
          <label className="opportunity-field">
            <span>Rol</span>
            <Select value={role} onChange={(e) => setRole(e.target.value as "user" | "admin")} required>
              <option value="user">Usuario</option>
              <option value="admin">Administrador</option>
            </Select>
          </label>
          {formErr ? <p className="error-text">{formErr}</p> : null}
          <Button type="submit" className="cta-button" disabled={createMut.isPending}>
            {createMut.isPending ? <Loader2 className="spin" size={16} aria-hidden /> : null}
            Crear usuario
          </Button>
        </form>

        <h2 className="opportunity-card-subtitle" style={{ marginTop: "2rem" }}>
          Cuentas
        </h2>
        {listQuery.isLoading ? <p className="muted-text">Cargando…</p> : null}
        {listQuery.isError ? <p className="error-text">No se pudo cargar el listado.</p> : null}
        {listQuery.data ? (
          <ul className="admin-users-list">
            {listQuery.data.items.map((u) => (
              <li key={u.user_id} className="admin-users-list-item">
                <strong>{u.display_name}</strong>
                <span className="muted-text">{u.email}</span>
                <span className="opportunity-summary-badge opportunity-summary-badge--muted">{u.role}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </Card>
    </div>
  );
}
