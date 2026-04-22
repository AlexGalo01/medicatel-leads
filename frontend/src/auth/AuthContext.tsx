import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { authLogin, authMe, getAccessToken, setAccessToken } from "../api";
import type { UserPublic } from "../types";

type AuthStatus = "unknown" | "authed" | "anon";

type AuthContextValue = {
  user: UserPublic | null;
  status: AuthStatus;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [status, setStatus] = useState<AuthStatus>("unknown");

  const refresh = useCallback(async () => {
    const t = getAccessToken();
    if (!t) {
      setUser(null);
      setStatus("anon");
      return;
    }
    try {
      const u = await authMe();
      setUser(u);
      setStatus("authed");
    } catch {
      setAccessToken(null);
      setUser(null);
      setStatus("anon");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await authLogin(email, password);
    setAccessToken(r.access_token);
    setUser(r.user);
    setStatus("authed");
  }, []);

  const logout = useCallback(() => {
    setAccessToken(null);
    setUser(null);
    setStatus("anon");
  }, []);

  const value = useMemo(
    () => ({ user, status, login, logout, refresh }),
    [user, status, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const v = useContext(AuthContext);
  if (!v) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return v;
}
