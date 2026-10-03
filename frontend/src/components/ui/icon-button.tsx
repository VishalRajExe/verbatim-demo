"use client";

import type { ComponentType } from "react";
import { Button, type ButtonProps } from "./button";
import { Tip } from "./tooltip";

type IconButtonProps = Omit<ButtonProps, "children"> & {
  label: string;
  icon: ComponentType<{ className?: string }>;
  side?: "top" | "bottom" | "left" | "right";
};

/** Icon-only button: always has a tooltip and an accessible name. */
export function IconButton({ label, icon: Icon, side, variant = "ghost", size = "icon", ...props }: IconButtonProps) {
  return (
    <Tip label={label} side={side}>
      <span className="inline-flex">
        <Button aria-label={label} variant={variant} size={size} {...props}>
          <Icon />
        </Button>
      </span>
    </Tip>
  );
}
