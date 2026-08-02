import { type ReactNode } from "react";
import { cn } from "@/src/lib/utils/cn";

interface CardProps {
  children: ReactNode;
  className?: string;
  variant?: "default" | "elevated" | "outline" | "glass";
  padding?: "none" | "sm" | "md" | "lg";
}

export function Card({ children, className, variant = "default", padding = "md" }: CardProps) {
  return (
    <div
      className={cn(
        "h-full rounded-[32px] transition-all",
        {
          "bg-white shadow-sm": variant === "default",
          "bg-white shadow-xl": variant === "elevated",
          "border border-mist bg-white/50": variant === "outline",
          "border border-white/50 bg-white/60 backdrop-blur-xl": variant === "glass",
        },
        {
          "p-0": padding === "none",
          "p-4": padding === "sm",
          "p-6": padding === "md",
          "p-8": padding === "lg",
        },
        className
      )}
    >
      {children}
    </div>
  );
}
