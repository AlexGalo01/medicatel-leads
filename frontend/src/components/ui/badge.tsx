import type { HTMLAttributes } from "react";

import { cn } from "../../lib/utils";

type BadgeVariant = "default" | "muted" | "success";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

export function Badge({ className, variant = "default", ...props }: BadgeProps): JSX.Element {
  return <span className={cn("ui-badge", `ui-badge--${variant}`, className)} {...props} />;
}

