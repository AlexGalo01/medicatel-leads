import { useAuth } from "./AuthContext";
import type { Permission } from "../types";

export function usePermissions() {
  const { user } = useAuth();

  const hasPermission = (perm: Permission): boolean => {
    if (!user) return false;
    if (user.role === "admin") return true;
    return (user.permissions ?? []).includes(perm);
  };

  return {
    hasPermission,
    canSearch: hasPermission("use_search"),
    canManageOpportunities: hasPermission("manage_opportunities"),
    isAdmin: user?.role === "admin",
  };
}
