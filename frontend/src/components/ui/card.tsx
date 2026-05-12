import type { HTMLAttributes } from "react";

import { cn } from "../../lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>): JSX.Element {
  return <div className={cn("ui-card", className)} {...props} />;
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>): JSX.Element {
  return <div className={cn("ui-card-content", className)} {...props} />;
}

