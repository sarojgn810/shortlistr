import {
  LayoutDashboard,
  Radar,
  Kanban,
  Send,
  BookOpen,
  BarChart2,
  FileText,
  UserCircle,
  Plug,
  Settings,
  Linkedin,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  icon: LucideIcon;
  label: string;
  href: string;
  /** When true, only exact path matches (children have their own nav entries). */
  exact?: boolean;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Work",
    items: [
      { icon: LayoutDashboard, label: "Today",    href: "/dashboard" },
      { icon: Radar,           label: "Discover", href: "/inbox" },
      { icon: Kanban,          label: "Pipeline", href: "/pipeline" },
      { icon: Send,            label: "Apply",    href: "/apply" },
      { icon: BookOpen,        label: "Prep",     href: "/prep" },
    ],
  },
  {
    label: "Insights",
    items: [{ icon: BarChart2, label: "Reports", href: "/reports" }],
  },
  {
    label: "Assets",
    items: [
      { icon: FileText,   label: "Resume",   href: "/cv" },
      { icon: Linkedin,   label: "LinkedIn", href: "/linkedin" },
      { icon: UserCircle, label: "Profile",  href: "/profile" },
    ],
  },
];

export const NAV_SYSTEM: NavItem[] = [
  { icon: Plug,     label: "Connections", href: "/connections" },
  { icon: Settings, label: "Settings",    href: "/settings" },
];

export const LINKEDIN_TABS = [
  { id: "overview", label: "Overview" },
  { id: "headline", label: "Headline" },
  { id: "about", label: "About" },
  { id: "experience", label: "Experience" },
  { id: "keywords", label: "Keywords" },
  { id: "visibility", label: "Visibility" },
  { id: "cover", label: "Cover" },
  { id: "preview", label: "Preview" },
  { id: "export", label: "Export" },
] as const;

export type LinkedInTabId = (typeof LINKEDIN_TABS)[number]["id"];
