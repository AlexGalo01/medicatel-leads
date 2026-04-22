import { Loader2 } from "lucide-react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "./AuthContext";

export function RequireAuth({ children }: { children: JSX.Element }): JSX.Element {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "unknown") {
    return (
      <div className="auth-loading-screen">
        <Loader2 className="spin" aria-hidden />
        <span>Comprobando sesión…</span>
      </div>
    );
  }

  if (status === "anon") {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  return children;
}
