import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";

import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";

export function LoginPage(): JSX.Element {
  const { login, status, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from || "/search";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (status === "authed" && user) {
      navigate(from, { replace: true });
    }
  }, [status, user, from, navigate]);

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
    setSubmitting(true);
    void login(email.trim(), password)
      .then(() => {
        navigate(from, { replace: true });
      })
      .catch((ex: Error) => {
        setErr(ex.message || "No se pudo iniciar sesión.");
      })
      .finally(() => {
        setSubmitting(false);
      });
  };

  return (
    <div className="auth-login-page">
      <Card className="panel auth-login-card">
        <h1 className="auth-login-title">Iniciar sesión</h1>
        <p className="muted-text auth-login-sub">Medicatel CRM — Lead Finder</p>
        <form className="auth-login-form" onSubmit={onSubmit}>
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
            <span>Contraseña</span>
            <Input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {err ? <p className="error-text">{err}</p> : null}
          <Button type="submit" className="cta-button auth-login-submit" disabled={submitting}>
            {submitting ? <Loader2 className="spin" size={16} aria-hidden /> : null}
            Entrar
          </Button>
        </form>
      </Card>
    </div>
  );
}
