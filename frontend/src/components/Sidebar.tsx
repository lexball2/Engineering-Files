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
      width: 280, minWidth: 280, height: "100vh", display: "flex", flexDirection: "column",
      position: "fixed", left: 0, top: 0, zIndex: 50, padding: "24px 16px",
      transition: "width 0.25s, padding 0.25s",
    }}>
      {!collapsed ? (
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "0 8px", marginBottom: 28 }}>
          <div style={{ width: 49, height: 49, borderRadius: "var(--radius)", background: "var(--primary)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <LayoutDashboard size={27} color="var(--on-primary)" />
          </div>
          <div style={{ overflow: "hidden" }}>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--primary)", lineHeight: 1.2, whiteSpace: "nowrap" }}>Insight Engine</h1>
            <p style={{ fontSize: 17, letterSpacing: 0, color: "var(--text-muted)", textTransform: "uppercase", whiteSpace: "nowrap" }}>Knowledge Base</p>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 28 }}>
          <div style={{ width: 45, height: 45, borderRadius: "var(--radius)", background: "var(--primary)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <LayoutDashboard size={25} color="var(--on-primary)" />
          </div>
        </div>
      )}

      {!collapsed && role !== "guest" && (
        <div style={{ display: "flex", alignItems: "center", gap: 9, margin: "0 8px 16px", padding: "13px 17px", borderRadius: "var(--radius)", background: "rgba(128,128,128,0.08)", border: "1px solid var(--border-glass)" }}>
          <Search size={23} color="var(--text-muted)" />
          <input placeholder="搜索知识库..." style={{ background: "none", border: "none", outline: "none", color: "var(--text-primary)", fontSize: 19, width: "100%" }} />
        </div>
      )}

      <nav style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
        {visibleLinks.map(({ to, icon: Icon, label }) => {
          const isActive = pathname === to || (to === "/dashboard" && pathname === "/");
          return (
            <button key={to} onClick={() => nav(to)} title={collapsed ? label : undefined} style={{
              display: "flex", alignItems: "center", gap: 12, width: "100%",
              padding: collapsed ? "17px 0" : "17px 19px",
              justifyContent: collapsed ? "center" : "flex-start",
              borderRadius: "var(--radius)",
              background: isActive ? "var(--primary-container)" : "transparent",
              color: isActive ? "var(--primary)" : "var(--text-muted)",
              fontSize: 20, fontWeight: isActive ? 600 : 400,
              borderLeft: !collapsed && isActive ? "4px solid var(--primary)" : "4px solid transparent",
              transition: "all 0.2s",
            }}>
              <Icon size={25} />
              {!collapsed && <span>{label}</span>}
            </button>
          );
        })}
      </nav>

      <div style={{ marginTop: "auto", paddingTop: 16, borderTop: "1px solid var(--border-subtle)", display: "flex", flexDirection: "column", gap: 8 }}>
        <button onClick={onToggleTheme} title={lightMode ? "深色模式" : "浅色模式"} style={{
          display: "flex", alignItems: "center", gap: 10, width: "100%",
          padding: collapsed ? "8px 0" : "8px 8px",
          justifyContent: collapsed ? "center" : "flex-start",
          borderRadius: "var(--radius-sm)", background: "transparent",
          color: "var(--text-muted)", fontSize: 19,
        }}>
          {lightMode ? <Moon size={collapsed ? 25 : 23} /> : <Sun size={collapsed ? 25 : 23} />}
          {!collapsed && <span>{lightMode ? "深色模式" : "浅色模式"}</span>}
        </button>

        {!collapseLocked && <button onClick={onToggleCollapse} title={collapsed ? "展开侧边栏" : "折叠侧边栏"} style={{
          display: "flex", alignItems: "center", gap: 10, width: "100%",
          padding: collapsed ? "8px 0" : "8px 8px",
          justifyContent: collapsed ? "center" : "flex-start",
          borderRadius: "var(--radius-sm)", background: "transparent",
          color: "var(--text-muted)", fontSize: 19,
        }}>
          {collapsed ? <PanelLeft size={25} /> : <PanelLeftClose size={23} />}
          {!collapsed && <span>折叠侧边栏</span>}
        </button>}

        <div style={{ display: "flex", alignItems: "center", justifyContent: collapsed ? "center" : "space-between", color: "var(--text-muted)", fontSize: 19 }}>
          {!collapsed && <div style={{ display: "flex", alignItems: "center", gap: 8 }}><User size={23} /><span>{username}</span></div>}
          <button onClick={onLogout} title="退出登录" style={{ background: "none", color: "var(--text-muted)", padding: 6, display: "flex" }}>
            <LogOut size={23} />
          </button>
        </div>
      </div>
    </aside>
  );
}
