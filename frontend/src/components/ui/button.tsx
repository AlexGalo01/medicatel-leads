import type { ButtonHTMLAttributes } from "react";

import { cn } from "../../lib/utils";

type ButtonVariant = "default" | "secondary" | "outline" | "ghost";
type ButtonSize = "default" | "sm" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

export function Button({ className, variant = "default", size = "default", type = "button", ...props }: ButtonProps): JSX.Element {
  return (
    <button
      type={type}
      className={cn("ui-btn", `ui-btn--${variant}`, `ui-btn--${size}`, className)}
      {...props}
    />
  );
}

