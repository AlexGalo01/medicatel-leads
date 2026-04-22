import type { SelectHTMLAttributes } from "react";

import { cn } from "../../lib/utils";

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>): JSX.Element {
  return <select className={cn("ui-select", className)} {...props} />;
}

