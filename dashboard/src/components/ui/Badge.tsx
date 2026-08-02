import { cn } from "@/src/lib/utils/cn";
import type { ReactNode } from "react";

interface BadgeProps {
  children: ReactNode;
  variant?: "default" | "lime" | "orange" | "success" | "warning" | "error" | "score";
  size?: "sm" | "md";
  className?: string;
}

export function Badge({ children, variant = "default", size = "sm", className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full font-medium",
        {
          "bg-mist text-stone": variant === "default",
          "bg-lime/20 text-black": variant === "lime",
          "bg-orange/20 text-orange": variant === "orange",
          "bg-success-soft text-success": variant === "success",
          "bg-warning-soft text-warning": variant === "warning",
          "bg-danger-soft text-danger": variant === "error",
          "bg-black text-lime": variant === "score",
        },
        {
          "px-2.5 py-1 text-sm": size === "sm",
          "px-3 py-1 text-sm": size === "md",
        },
        className
      )}
    >
      {children}
    </span>
  );
}
