import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import type { UserRole } from "@/types/api";

interface Props {
  allow: UserRole[];
  children: React.ReactNode;
  fallback?: string;
}

/**
 * Render children only if the current user's role is in `allow`.
 * Otherwise redirect to `fallback` (default: /).
 */
export function RoleGate({ allow, children, fallback = "/" }: Props) {
  const role = useAuthStore((s) => s.role);

  if (!role || !allow.includes(role as UserRole)) {
    return <Navigate to={fallback} replace />;
  }
  return <>{children}</>;
}
