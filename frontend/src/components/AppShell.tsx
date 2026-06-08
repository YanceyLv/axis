import {
  BarChart3,
  BellRing,
  BookOpen,
  Eye,
  Home,
  LogOut,
  Rocket,
  Settings,
  Sparkles,
} from "lucide-react";
import type { ReactNode } from "react";

export type ViewKey =
  | "dashboard"
  | "strategies"
  | "signals"
  | "signal-detail"
  | "new-coins"
  | "watchlist"
  | "watch-detail"
  | "knowledge"
  | "settings";

interface AppShellProps {
  activeView: ViewKey;
  onNavigate: (view: ViewKey) => void;
  userEmail: string;
  onLogout: () => void;
  children: ReactNode;
}

const navItems: Array<{
  key: ViewKey;
  label: string;
  icon: typeof Home;
}> = [
  { key: "dashboard", label: "首页", icon: Home },
  { key: "strategies", label: "策略中心", icon: Sparkles },
  { key: "signals", label: "信号中心", icon: BellRing },
  { key: "new-coins", label: "新币检测", icon: Rocket },
  { key: "watchlist", label: "观察池", icon: Eye },
  { key: "knowledge", label: "知识库", icon: BookOpen },
];

export function AppShell({ activeView, onNavigate, userEmail, onLogout, children }: AppShellProps) {
  return (
    <div className="shell">
      <aside className="sidebar" aria-label="TrendAI 主导航">
        <div className="brand">
          <div className="brand-mark">
            <BarChart3 size={22} aria-hidden="true" />
          </div>
          <span>TrendAI</span>
        </div>

        <nav className="nav" aria-label="主导航">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive =
              activeView === item.key ||
              (activeView === "signal-detail" && item.key === "signals") ||
              (activeView === "watch-detail" && item.key === "watchlist");

            return (
              <button
                className={`nav-item${isActive ? " active" : ""}`}
                aria-label={item.label}
                key={item.key}
                onClick={() => onNavigate(item.key)}
                type="button"
              >
                <Icon size={18} aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-account">
          <span>{userEmail}</span>
          <button className="settings-button" type="button" aria-label="退出登录" onClick={onLogout}>
            <LogOut size={18} aria-hidden="true" />
            <span>退出登录</span>
          </button>
          <button className="settings-button" type="button" aria-label="设置" onClick={() => onNavigate("settings")}>
            <Settings size={18} aria-hidden="true" />
            <span>设置</span>
          </button>
        </div>
      </aside>

      <main className="main">{children}</main>
    </div>
  );
}
