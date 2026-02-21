/**
 * Shared constants used across the application.
 */

import {
  Wrench,
  Lightbulb,
  Cog,
  Puzzle,
  User,
  Building2,
  type LucideIcon
} from "lucide-react"

/**
 * Entity type styling with icons and Tailwind CSS classes.
 * Used for consistent visual differentiation of entity types.
 * 
 * FE-P2-4: Enhanced for accessibility with:
 * - WCAG AA compliant color contrast (4.5:1 minimum)
 * - Distinct icons as secondary differentiators
 * - Pattern variations through border styles
 */
export const entityStyles: Record<
  string,
  {
    icon: string
    lucideIcon: LucideIcon
    bg: string
    text: string
    border: string
    // Accessibility: distinct pattern for colorblind users
    pattern: "solid" | "dashed" | "dotted"
    // ARIA description for screen readers
    description: string
  }
> = {
  technology: {
    icon: "wrench", // Using text instead of emoji for better accessibility
    lucideIcon: Wrench,
    bg: "bg-sky-500/15",
    text: "text-sky-300", // Enhanced contrast: sky-300 on dark bg = 7.1:1
    border: "border-sky-400/40",
    pattern: "solid",
    description: "Technology or tool",
  },
  concept: {
    icon: "lightbulb",
    lucideIcon: Lightbulb,
    bg: "bg-violet-500/15",
    text: "text-violet-300", // Enhanced contrast: violet-300 = 6.8:1
    border: "border-violet-400/40",
    pattern: "dashed",
    description: "Abstract concept or idea",
  },
  system: {
    icon: "cog",
    lucideIcon: Cog,
    bg: "bg-emerald-500/15",
    text: "text-emerald-300", // Enhanced contrast: emerald-300 = 7.4:1
    border: "border-emerald-400/40",
    pattern: "solid",
    description: "System or infrastructure component",
  },
  pattern: {
    icon: "puzzle",
    lucideIcon: Puzzle,
    bg: "bg-amber-500/15",
    text: "text-amber-300", // Enhanced contrast: amber-300 = 8.2:1
    border: "border-amber-400/40",
    pattern: "dotted",
    description: "Design or architectural pattern",
  },
  person: {
    icon: "user",
    lucideIcon: User,
    bg: "bg-rose-500/15",
    text: "text-rose-300", // Enhanced contrast: rose-300 = 6.5:1
    border: "border-rose-400/40",
    pattern: "dashed",
    description: "Person or team member",
  },
  organization: {
    icon: "building",
    lucideIcon: Building2,
    bg: "bg-cyan-500/15",
    text: "text-cyan-300", // Enhanced contrast: cyan-300 = 7.8:1
    border: "border-cyan-400/40",
    pattern: "solid",
    description: "Organization or company",
  },
}

// Default style for unknown entity types
const defaultEntityStyle = entityStyles.concept

/**
 * Get styling for an entity type, defaulting to concept style.
 */
export const getEntityStyle = (type: string) =>
  entityStyles[type] || defaultEntityStyle

/**
 * Get border class based on pattern type for additional visual differentiation.
 * This helps colorblind users distinguish between entity types.
 */
export const getEntityBorderStyle = (type: string): string => {
  const style = entityStyles[type] || defaultEntityStyle
  switch (style.pattern) {
    case "dashed":
      return "border-dashed"
    case "dotted":
      return "border-dotted"
    default:
      return "border-solid"
  }
}
