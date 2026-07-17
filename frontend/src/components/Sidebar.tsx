import { useLocation, useNavigate } from "react-router-dom";
import { FileImage, FileText, LayoutDashboard, LogOut, MessageSquare, Moon, PanelLeft, PanelLeftClose, Search, ShieldCheck, Sun, User } from "lucide-react";
import type { UserRole } from "../api/auth";

interface Props {
  username: string;
  role: UserRole;
  onLogout: () => void;
  collapsed: boolean;
  collapseLocked: boolean;
  onToggleCollapse: () => void;
  lightMode: boolean;
  onToggleTheme: () => void;
}

const staffLinks = [
  { to: "/dashboard", icon: LayoutDashboard, label: "仪表盘" },
  { to: "/chat", icon: MessageSquare, label: "知识问答" },
  { to: "/documents", icon: FileText, label: "文档管理" },
  { to: "/image-assets", icon: FileImage, label: "图片资产" },
];

export default function Sidebar({ username, role, onLogout, collapsed, collapseLocked, onToggleCollapse, lightMode, onToggleTheme }: Props) {
  const { pathname } = useLocation();
  const nav = useNavigate();
  const guestLinks = [{ to: "/chat", icon: MessageSquare, label: "知识问答" }];
  const baseLinks = role === "guest" ? guestLinks : staffLinks;
  const visibleLinks = role === "admin" ? [...baseLinks, { to: "/admin/users", icon: ShieldCheck, label: "用户权限" }] : baseLinks;

  return (
    <aside className={"glass-sidebar" + (collapsed ? " sidebar-collapsed" : "")} style={{
      width: 220, minWidth: 220, height: "100vh", display: "flex", flexDirection: "column",
      position: "fixed", left: 0, top: 0, zIndex: 50, padding: "16px 10px",
      transition: "width 0.25s, padding 0.25s",
    }}>
      {!collapsed ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 6px", marginBottom: 18 }}>
          <div style={{ width: 34, height: 34, borderRadius: "var(--radius)", background: "var(--primary)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <LayoutDashboard size={18} color="var(--on-primary)" />
          </div>
          <div style={{ overflow: "hidden" }}>
            <h1 style={{ fontSize: 14, fontWeight: 700, color: "var(--primary)", lineHeight: 1.2, whiteSpace: "nowrap" }}>Insight Engine</h1>
            <p style={{ fontSize: 12, letterSpacing: 0, color: "var(--text-muted)", textTransform: "uppercase", whiteSpace: "nowrap" }}>Knowledge Base</p>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 18 }}>
          <div style={{ width: 32, height: 32, borderRadius: "var(--radius)", background: "var(--primary)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <LayoutDashboard size={16} color="var(--on-primary)" />
          </div>
        </div>
      )}

      {!collapsed && role !== "guest" && (
        <div style={{ display: "flex", alignItems: "center", gap: 7, margin: "0 6px 12px", padding: "8px 10px", borderRadius: "var(--radius)", background: "rgba(128,128,128,0.08)", border: "1px solid var(--border-glass)" }}>
          <Search size={16} color="var(--text-muted)" />
          <input placeholder="搜索知识库..." style={{ background: "none", border: "none", outline: "none", color: "var(--text-primary)", fontSize: 12, width: "100%" }} />
        </div>
      )}

      <nav style={{ flex: 1, display: "flex", flexDirection: "column", gap: 3 }}>
        {visibleLinks.map(({ to, icon: Icon, label }) => {
          const isActive = pathname === to || (to === "/dashboard" && pathname === "/");
          return (
            <button key={to} onClick={() => nav(to)} title={collapsed ? label : undefined} style={{
              display: "flex", alignItems: "center", gap: 8, width: "100%",
              padding: collapsed ? "10px 0" : "10px 12px",
              justifyContent: collapsed ? "center" : "flex-start",
              borderRadius: "var(--radius)",
              background: isActive ? "var(--primary-container)" : "transparent",
              color: isActive ? "var(--primary)" : "var(--text-muted)",
              fontSize: 12, fontWeight: isActive ? 600 : 400,
              borderLeft: !collapsed && isActive ? "3px solid var(--primary)" : "3px solid transparent",
              transition: "all 0.2s",
            }}>
              <Icon size={16} />
              {!collapsed && <span>{label}</span>}
            </button>
          );
        })}
      </nav>

      <div style={{ marginTop: "auto", paddingTop: 10, borderTop: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column", gap: 5 }}>
        <button onClick={onToggleTheme} title={lightMode ? "深色模式" : "浅色模式"} style={{
          display: "flex", alignItems: "center", gap: 7, width: "100%",
          padding: collapsed ? "6px 0" : "6px 7px",
          justifyContent: collapsed ? "center" : "flex-start",
          borderRadius: "var(--radius-sm)", background: "transparent",
          color: "var(--text-muted)", fontSize: 12,
        }}>
          {lightMode ? <Moon size={16} /> : <Sun size={16} />}
          {!collapsed && <span>{lightMode ? "深色模式" : "浅色模式"}</span>}
        </button>

        {!collapseLocked && <button onClick={onToggleCollapse} title={collapsed ? "展开侧边栏" : "折叠侧边栏"} style={{
          display: "flex", alignItems: "center", gap: 7, width: "100%",
          padding: collapsed ? "6px 0" : "6px 7px",
          justifyContent: collapsed ? "center" : "flex-start",
          borderRadius: "var(--radius-sm)", background: "transparent",
          color: "var(--text-muted)", fontSize: 12,
        }}>
          {collapsed ? <PanelLeft size={16} /> : <PanelLeftClose size={16} />}
          {!collapsed && <span>折叠侧边栏</span>}
        </button>}

        <div style={{ display: "flex", alignItems: "center", justifyContent: collapsed ? "center" : "space-between", color: "var(--text-muted)", fontSize: 12 }}>
          {!collapsed && <div style={{ display: "flex", alignItems: "center", gap: 6 }}><User size={16} /><span>{username}</span></div>}
          <button onClick={onLogout} title="退出登录" style={{ background: "none", color: "var(--text-muted)", padding: 6, display: "flex" }}>
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </aside>
  );
}
