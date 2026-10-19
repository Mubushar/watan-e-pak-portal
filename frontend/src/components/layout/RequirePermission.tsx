/** Show a dashboard page only to users holding a permission — or any of several (the API enforces the same rule). */
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ShieldAlert } from "lucide-react";
import { useAuth } from "@/store/auth";
import { EmptyState } from "@/components/ui";

export function RequirePermission({ perm, area, children }: { perm: string | string[]; area: string; children: ReactNode }) {
  const can = useAuth((s) => s.can);
  useAuth((s) => s.user);
  const perms = Array.isArray(perm) ? perm : [perm];
  if (perms.some((p) => can(p))) return <>{children}</>;
  return (
    <div className="mx-auto max-w-xl py-16">
      <EmptyState
        icon={<ShieldAlert className="h-6 w-6" />}
        title={`No access to ${area}`}
        hint={`Your role doesn't include ${area}. Ask an administrator to grant the “${perms.join("” or “")}” permission.`}
        action={
          <Link to="/app" className="btn btn-outline btn-sm">
            Back to dashboard
          </Link>
        }
      />
    </div>
  );
}
