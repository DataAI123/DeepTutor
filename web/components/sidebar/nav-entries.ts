import {
  Clapperboard,
  BookOpen,
  BookText,
  Bot,
  Brain,
  HeartHandshake,
  House,
  LayoutGrid,
  Library,
  PenLine,
  Route,
  Settings,
  type LucideIcon,
} from "lucide-react";

import type { Capability } from "@/lib/capability-routes";

export interface NavEntry {
  href: string;
  label: string;
  icon: LucideIcon;
  tooltipKey?: string;
  /** Model capability this feature needs; locked when the user lacks it. */
  requires?: Capability;
}

/**
 * The workspace features, in the order they ship in.
 *
 * This is the *default* arrangement, not the rendered one — a learner can
 * reorder these and fold the ones they don't use into "More"
 * (``lib/sidebar-layout.ts``). Adding an entry here places it for everyone,
 * including people who have already arranged their sidebar: it arrives next to
 * the neighbour it follows below rather than at the bottom of their list.
 */
export const PRIMARY_NAV: NavEntry[] = [
  {
    href: "/chat",
    label: "Home",
    icon: House,
    tooltipKey: "Home tooltip",
    requires: "llm",
  },
  {
    href: "/partners",
    label: "Partners",
    icon: HeartHandshake,
    tooltipKey: "Partners tooltip",
    requires: "llm",
  },
  {
    href: "/co-writer",
    label: "Co-Writer",
    icon: PenLine,
    tooltipKey: "Co-Writer tooltip",
    requires: "llm",
  },
  {
    href: "/books",
    label: "Book",
    icon: Library,
    tooltipKey: "Book tooltip",
    requires: "llm",
  },
  // Courses nav entry temporarily hidden pending further product work.
  // The route and its data are untouched — only this entry point is gone.
  {
    href: "/mastery",
    label: "Mastery Path",
    icon: Route,
    tooltipKey: "Learn through a living mastery map",
    requires: "llm",
  },
  {
    href: "/reading",
    label: "Immersive Reading",
    icon: BookText,
    tooltipKey: "Immersive Reading tooltip",
    requires: "llm",
  },
  {
    href: "/space",
    label: "Learning Space",
    icon: LayoutGrid,
    tooltipKey: "Space tooltip",
  },
];

/** The one console row: it owns the second level below it. */
export const SECONDARY_NAV: NavEntry[] = [
  { href: "/settings", label: "Settings", icon: Settings },
];

/**
 * The second level under Settings — the consoles and the account rows that used
 * to sit in their own nav rows. They keep their own routes; only the entry
 * point moved.
 */
export const SETTINGS_SUB_NAV: NavEntry[] = [
  {
    // Knowledge Center is a console for managing KBs and retrieval engines, not
    // a daily workspace. Never gated — embedding / search are shared admin
    // infrastructure, no per-user model grant needed.
    href: "/knowledge-bases",
    label: "Knowledge Center",
    icon: BookOpen,
    tooltipKey: "Knowledge tooltip",
  },
  {
    // Memory inspects and curates the tutor's long-term memory. Never gated —
    // memory has no per-user model requirement.
    href: "/memory",
    label: "Memory",
    icon: Brain,
    tooltipKey: "Memory tooltip",
  },
  {
    // My Agents: connect a live local Claude Code / Codex to consult in chat,
    // and manage imported agent conversations. Ungated — managing connections
    // and imports needs no per-user model grant.
    href: "/agents",
    label: "My Agents",
    icon: Bot,
    tooltipKey: "Agents tooltip",
  },
  {
    href: "/watching",
    label: "Immersive Watching",
    icon: Clapperboard,
    tooltipKey: "Watch videos with a grounded AI companion.",
  },
];

export const PRIMARY_NAV_HREFS = PRIMARY_NAV.map((entry) => entry.href);

export const NAV_BY_HREF = new Map(
  [...PRIMARY_NAV, ...SECONDARY_NAV, ...SETTINGS_SUB_NAV].map((entry) => [
    entry.href,
    entry,
  ]),
);

export function isNavActive(pathname: string, href: string) {
  if (href === "/space") {
    return (
      (pathname === "/space" || pathname.startsWith("/space/")) &&
      !pathname.startsWith("/mastery")
    );
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}
