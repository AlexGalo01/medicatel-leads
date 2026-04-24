import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";

import { authRegister, setAccessToken } from "../api";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";

export function RegisterPage(): JSX.Element {
  const { status, user, refresh } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (status === "authed" && user) {
      navigate("/search", { replace: true });
    }
  }, [status, user, navigate]);

  if (status === "unknown") {
    return (
      <div className="auth-loading-screen">
        <Loader2 className="spin" aria-hidden />
        <span>Comprobando sesión…</span>
      </div>
    );
  }

  if (status === "authed" && user) {
    return (
      <div className="auth-loading-screen">
        <Loader2 className="spin" aria-hidden />
        <span>Redirigiendo…</span>
      </div>
    );
  }

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (password !== password2) {
      setErr("Las contraseñas no coinciden.");
      return;
    }
    if (password.length < 8) {
      setErr("La contraseña debe tener al menos 8 caracteres.");
      return;
    }
    setSubmitting(true);
    void authRegister({ email: email.trim(), display_name: displayName.trim(), password })
      .then(async (r) => {
        setAccessToken(r.access_token);
        await refresh();
        navigate("/search", { replace: true });
      })
      .catch((ex: Error) => {
        setErr(ex.message || "No se pudo completar el registro.");
      })
      .finally(() => {
        setSubmitting(false);
      });
  };

  return (
    <div className="auth-login-page">
      <Card className="panel auth-login-card">
        <h1 className="auth-login-title">Crear cuenta</h1>
        <p className="muted-text auth-login-sub">AI CRM — Lead Finder</p>
        <form className="auth-login-form" onSubmit={onSubmit}>
          <label className="opportunity-field">
            <span>Nombre visible</span>
            <Input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              autoComplete="name"
              required
            />
          </label>
          <label className="opportunity-field">
            <span>Correo</span>
            <Input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label className="opportunity-field">
            <span>Contraseña (mín. 8)</span>
            <Input
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={8}
              required
            />
          </label>
          <label className="opportunity-field">
            <span>Confirmar contraseña</span>
            <Input
              type="password"
              autoComplete="new-password"
              value={password2}
              onChange={(e) => setPassword2(e.target.value)}
              minLength={8}
              required
            />
          </label>
          {err ? <p className="error-text">{err}</p> : null}
          <Button type="submit" className="cta-button auth-login-submit" disabled={submitting}>
            {submitting ? <Loader2 className="spin" size={16} aria-hidden /> : null}
            Registrarse
          </Button>
        </form>
        <p className="muted-text" style={{ marginTop: "1rem", textAlign: "center", fontSize: "14px" }}>
          ¿Ya tienes cuenta?{" "}
          <Link to="/login" className="link-button" style={{ display: "inline" }}>
            Iniciar sesión
          </Link>
        </p>
      </Card>
    </div>
  );
}
