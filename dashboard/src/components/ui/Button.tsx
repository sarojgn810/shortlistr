"use client";

import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/src/lib/utils/cn";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "lime";
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", isLoading, disabled, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={cn(
          "inline-flex items-center justify-center gap-2 font-semibold transition-all active:scale-95 disabled:cursor-not-allowed disabled:opacity-70",
          {
            "bg-black text-lime shadow-xl shadow-black/10 hover:scale-[1.02] hover:shadow-2xl":
              variant === "primary",
            "border border-mist bg-white text-ink hover:bg-sage/50": variant === "secondary",
            "bg-transparent text-stone hover:bg-mist/50 hover:text-ink": variant === "ghost",
            "bg-danger text-white hover:opacity-90": variant === "danger",
            "bg-lime text-black hover:bg-lime/80": variant === "lime",
          },
          {
            "rounded-xl px-4 py-2 text-sm": size === "sm",
            "rounded-2xl px-6 py-3 text-base": size === "md",
            "rounded-2xl px-8 py-4 text-lg": size === "lg",
          },
          className
        )}
        {...props}
      >
        {isLoading ? (
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" />
        ) : (
          children
        )}
      </button>
    );
  }
);

Button.displayName = "Button";
export { Button };
