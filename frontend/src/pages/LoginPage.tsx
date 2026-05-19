import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AlertCircle, Bot, Eye, EyeOff, Loader2, Lock, Mail } from "lucide-react";

import { useAuth } from "../auth/AuthContext";

const inputStyle: React.CSSProperties = {
  width: "100%",
  paddingTop: 10,
  paddingBottom: 10,
  fontSize: 14,
  fontFamily: "inherit",
  color: "#111827",
  backgroundColor: "#fff",
  border: "1px solid #D3D3D3",
  borderRadius: 8,
  outline: "none",
  boxSizing: "border-box",
  transition: "border-color 0.2s",
};

export function LoginPage(): JSX.Element {
  const { login, status, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from || "/search";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "#F3F4F6",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "var(--font-sans)",
        padding: "0 16px",
      }}
    >
      <div style={{ width: "100%", maxWidth: 420 }}>
        {/* Login Card */}
        <div
          style={{
            backgroundColor: "#fff",
            borderRadius: 16,
            border: "1px solid #E5E7EB",
            boxShadow: "0 10px 25px -5px rgba(0,0,0,0.06), 0 8px 10px -6px rgba(0,0,0,0.02)",
            padding: "40px",
          }}
        >
          {/* Branding */}
          <div style={{ textAlign: "center", marginBottom: 32 }}>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: 48,
                height: 48,
                borderRadius: 12,
                backgroundColor: "#EFF6FF",
                marginBottom: 16,
              }}
            >
              <Bot size={24} color="#0000FF" />
            </div>
            <h1
              style={{
                fontSize: 24,
                fontWeight: 700,
                color: "#111827",
                margin: 0,
                letterSpacing: "-0.025em",
                lineHeight: 1.2,
                fontFamily: "inherit",
              }}
            >
              LeadGen AI
            </h1>
            <p style={{ fontSize: 14, color: "#9CA3AF", marginTop: 4, fontWeight: 500, fontFamily: "inherit" }}>
              Lead Finder
            </p>
          </div>

          {/* Error Banner */}
          {err && (
            <div
              style={{
                backgroundColor: "rgba(239,68,68,0.08)",
                border: "1px solid rgba(239,68,68,0.2)",
                borderRadius: 8,
                padding: "10px 12px",
                display: "flex",
                alignItems: "flex-start",
                gap: 10,
                marginBottom: 24,
              }}
            >
              <AlertCircle size={16} color="#EF4444" style={{ marginTop: 2, flexShrink: 0 }} />
              <div>
                <p style={{ fontSize: 13, fontWeight: 600, color: "#EF4444", margin: 0, fontFamily: "inherit" }}>
                  Credenciales incorrectas
                </p>
                <p style={{ fontSize: 12, color: "rgba(239,68,68,0.8)", margin: "2px 0 0", fontFamily: "inherit" }}>
                  {err}
                </p>
              </div>
            </div>
          )}

          {/* Form */}
          <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {/* Email */}
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <label htmlFor="email" style={{ fontSize: 13, fontWeight: 600, color: "#374151", fontFamily: "inherit" }}>
                Correo electrónico
              </label>
              <div style={{ position: "relative" }}>
                <Mail
                  size={15}
                  color="#9CA3AF"
                  style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}
                />
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="tu@empresa.com"
                  required
                  style={{ ...inputStyle, paddingLeft: 36, paddingRight: 12 }}
                  onFocus={(e) => { e.target.style.borderColor = "#0000FF"; }}
                  onBlur={(e) => { e.target.style.borderColor = "#D3D3D3"; }}
                />
              </div>
            </div>

            {/* Password */}
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <label htmlFor="password" style={{ fontSize: 13, fontWeight: 600, color: "#374151", fontFamily: "inherit" }}>
                  Contraseña
                </label>
                <a href="#" style={{ fontSize: 12, fontWeight: 500, color: "#0000FF", textDecoration: "none", fontFamily: "inherit" }}>
                  ¿Olvidaste tu contraseña?
                </a>
              </div>
              <div style={{ position: "relative" }}>
                <Lock
                  size={13}
                  color="#9CA3AF"
                  style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}
                />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  style={{ ...inputStyle, paddingLeft: 36, paddingRight: 40 }}
                  onFocus={(e) => { e.target.style.borderColor = "#0000FF"; }}
                  onBlur={(e) => { e.target.style.borderColor = "#D3D3D3"; }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  style={{
                    position: "absolute",
                    right: 12,
                    top: "50%",
                    transform: "translateY(-50%)",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    padding: 0,
                    color: "#9CA3AF",
                    display: "flex",
                    alignItems: "center",
                  }}
                >
                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            {/* Remember me */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, paddingTop: 2 }}>
              <input
                id="remember-me"
                type="checkbox"
                style={{ width: 16, height: 16, accentColor: "#0000FF", cursor: "pointer", flexShrink: 0 }}
              />
              <label htmlFor="remember-me" style={{ fontSize: 13, color: "#6B7280", cursor: "pointer", fontFamily: "inherit" }}>
                Mantener sesión iniciada
              </label>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={submitting}
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                padding: "10px 16px",
                fontSize: 14,
                fontWeight: 600,
                fontFamily: "inherit",
                color: "#fff",
                backgroundColor: "#0000FF",
                border: "none",
                borderRadius: 8,
                cursor: submitting ? "not-allowed" : "pointer",
                opacity: submitting ? 0.75 : 1,
                transition: "background-color 0.2s, opacity 0.2s",
                marginTop: 4,
              }}
              onMouseEnter={(e) => { if (!submitting) e.currentTarget.style.backgroundColor = "#0000cc"; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "#0000FF"; }}
            >
              {submitting ? <Loader2 size={16} className="spin" aria-hidden /> : null}
              Entrar
            </button>
          </form>

          {/* Register link */}
          <p style={{ marginTop: 28, textAlign: "center", fontSize: 13, color: "#6B7280", fontFamily: "inherit" }}>
            ¿No tienes cuenta?{" "}
            <Link to="/registro" style={{ fontWeight: 600, color: "#0000FF", textDecoration: "none" }}>
              Regístrate
            </Link>
          </p>
        </div>

        {/* Footer links */}
        <div style={{ textAlign: "center", marginTop: 28, fontSize: 12, color: "#9CA3AF", fontFamily: "inherit" }}>
          <a href="#" style={{ color: "inherit", textDecoration: "none", marginRight: 8 }}>Términos</a>
          <span style={{ marginRight: 8 }}>•</span>
          <a href="#" style={{ color: "inherit", textDecoration: "none", marginRight: 8 }}>Privacidad</a>
          <span style={{ marginRight: 8 }}>•</span>
          <a href="#" style={{ color: "inherit", textDecoration: "none" }}>Soporte</a>
        </div>
      </div>
    </div>
  );
}
