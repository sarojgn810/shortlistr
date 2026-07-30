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
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  icon: LucideIcon;
  label: string;
  href: string;
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
      { icon: FileText,   label: "Resume",  href: "/cv" },
      { icon: UserCircle, label: "Profile", href: "/profile" },
    ],
  },
];

export const NAV_SYSTEM: NavItem[] = [
  { icon: Plug,     label: "Connections", href: "/connections" },
  { icon: Settings, label: "Settings",    href: "/settings" },
];
