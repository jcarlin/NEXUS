import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap transition-all duration-150 outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 active:scale-[0.98]",
  {
    variants: {
      variant: {
        default:
          "bg-gradient-to-b from-primary to-primary/80 text-primary-foreground shadow-[inset_0_1px_0_0_rgba(255,255,255,0.12),0_1px_2px_rgba(0,0,0,0.2)] hover:from-primary-hover hover:to-primary/85 hover:shadow-[inset_0_1px_0_0_rgba(255,255,255,0.12),0_1px_3px_rgba(0,0,0,0.25),0_0_12px_var(--color-primary)/15]",
        destructive:
          "bg-gradient-to-b from-destructive to-destructive/80 text-white shadow-[inset_0_1px_0_0_rgba(255,255,255,0.10),0_1px_2px_rgba(0,0,0,0.2)] hover:from-destructive hover:to-destructive/70 hover:shadow-[inset_0_1px_0_0_rgba(255,255,255,0.10),0_1px_3px_rgba(0,0,0,0.25)] focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40",
        outline:
          "border border-border/60 bg-transparent shadow-xs hover:bg-accent/50 hover:text-accent-foreground hover:border-border dark:border-border/50 dark:bg-white/[0.03] dark:hover:bg-white/[0.06]",
        secondary:
          "bg-secondary/80 text-secondary-foreground backdrop-blur-sm border border-white/[0.06] hover:bg-secondary/95 hover:border-white/[0.10]",
        ghost:
          "hover:bg-accent/50 hover:text-accent-foreground dark:hover:bg-white/[0.06]",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2 has-[>svg]:px-3",
        xs: "h-6 gap-1 rounded-md px-2 text-xs has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 rounded-md px-3 has-[>svg]:px-2.5",
        lg: "h-10 rounded-md px-6 has-[>svg]:px-4",
        icon: "size-9",
        "icon-xs": "size-6 rounded-md [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
