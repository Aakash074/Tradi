"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  History,
  LayoutDashboard,
  Shield,
  Zap,
} from "lucide-react";
import clsx from "clsx";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/strategies", label: "Strategies", icon: BarChart3 },
  { href: "/risk", label: "Risk Monitor", icon: Shield },
  { href: "/history", label: "History", icon: History },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex w-64 flex-col border-r border-zinc-800 bg-zinc-950 p-6">
      <div className="mb-8">
        <div className="flex items-center gap-2">
          <Zap className="h-8 w-8 text-accent" />
          <div>
            <h1 className="text-xl font-bold gradient-text">Tradi</h1>
            <p className="text-xs text-zinc-500">BNB Hackathon Agent</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-1">
        {navItems.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={clsx(
              "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
              pathname === href
                ? "bg-accent/10 text-accent"
                : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
      </nav>

      <div className="mt-auto rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <Activity className="h-3 w-3 text-green-500" />
          BSC Mainnet
        </div>
        <p className="mt-1 text-xs text-zinc-600">PancakeSwap V2/V3 Spot</p>
      </div>
    </aside>
  );
}
