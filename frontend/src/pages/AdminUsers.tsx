import { useCallback, useEffect, useState } from "react";
import { Search, ShieldCheck, Trash2, UserCheck, UserX, X } from "lucide-react";
import { api } from "../api/client";
import type { UserRole } from "../api/auth";

interface UserItem {
  id: number;
  username: string;
  role: UserRole;
  department: string;
  is_active: boolean;
  created_at: string;
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "请求失败";
}

export default function AdminUsers() {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState("");
  const [keyword, setKeyword] = useState("");
  const [activeKeyword, setActiveKeyword] = useState("");
  const currentUsername = localStorage.getItem("username") || "";

  const loadUsers = useCallback(async (nextKeyword: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      const trimmedKeyword = nextKeyword.trim();
      if (trimmedKeyword) params.set("username", trimmedKeyword);
      const query = params.toString();
      const res = await fetch(`/api/auth/users${query ? `?${query}` : ""}`, { credentials: "same-origin" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `请求失败 (${res.status})`);
      }
      setUsers(await res.json());
    } catch (error) {
      setToast(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, []);

  function searchUsers() {
    const trimmedKeyword = keyword.trim();
    setActiveKeyword(trimmedKeyword);
    loadUsers(trimmedKeyword);
  }

  function clearSearch() {
    setKeyword("");
    setActiveKeyword("");
    loadUsers("");
  }

  async function setRole(username: string, role: UserRole) {
    try {
      await api.post("/auth/users/role", { username, role });
      setToast("用户角色已更新");
      await loadUsers(activeKeyword);
    } catch (error) {
      setToast(getErrorMessage(error));
    }
  }

  async function setStatus(username: string, is_active: boolean) {
    try {
      await api.post("/auth/users/status", { username, is_active });
      setToast("用户状态已更新");
      await loadUsers(activeKeyword);
    } catch (error) {
      setToast(getErrorMessage(error));
    }
  }

  async function deleteUser(username: string) {
    if (!window.confirm(`确认删除用户「${username}」吗？删除后该账号将无法登录。`)) return;
    try {
      await api.post("/auth/users/delete", { username });
      setToast("用户已删除");
      await loadUsers(activeKeyword);
    } catch (error) {
      setToast(getErrorMessage(error));
    }
  }

  useEffect(() => {
    loadUsers("");
  }, [loadUsers]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--body-gradient)" }}>
      <header className="glass-nav page-header" style={{ height: 73, display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, zIndex: 40 }}>
        <h2 style={{ fontSize: 22, fontWeight: 700, color: "var(--primary)", display: "flex", alignItems: "center", gap: 9 }}>
          <ShieldCheck size={25} /> 用户权限
        </h2>
        <button onClick={() => loadUsers(activeKeyword)} disabled={loading} style={{ height: 45, padding: "0 19px", borderRadius: "var(--radius-sm)", background: "var(--primary-container)", color: "var(--primary)", fontWeight: 700 }}>
          {loading ? "刷新中..." : "刷新"}
        </button>
      </header>

      <main className="page-frame page-content">
        <section className="glass-panel" style={{ marginBottom: 16, padding: 16, display: "grid", gridTemplateColumns: "minmax(220px, 1fr) auto auto", gap: 10, alignItems: "center" }}>
          <label style={{ position: "relative", display: "flex", alignItems: "center" }}>
            <Search size={18} style={{ position: "absolute", left: 14, color: "var(--text-muted)" }} />
            <input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && searchUsers()}
              placeholder="按用户名查找"
              aria-label="按用户名查找"
              style={{ width: "100%", height: 40, padding: "0 14px 0 40px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-glass)", background: "var(--surface)", color: "var(--text-primary)" }}
            />
          </label>
          <button onClick={searchUsers} disabled={loading} style={{ height: 40, padding: "0 16px", borderRadius: "var(--radius-sm)", background: "var(--primary-solid)", color: "var(--on-primary)", fontWeight: 800, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7 }}>
            <Search size={18} /> 查找
          </button>
          <button onClick={clearSearch} disabled={loading && !activeKeyword} style={{ height: 40, padding: "0 16px", borderRadius: "var(--radius-sm)", background: "var(--surface)", color: "var(--text-primary)", fontWeight: 700, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7 }}>
            <X size={18} /> 清空
          </button>
        </section>

        <section className="glass-panel admin-table-wrap" style={{ borderRadius: "var(--radius-lg)" }}>
          <table className="admin-users-table" style={{ width: "100%", borderCollapse: "collapse", color: "var(--text-primary)" }}>
            <thead>
              <tr style={{ color: "var(--text-muted)", fontSize: 18, textAlign: "left" }}>
                <th style={{ padding: 16 }}>用户</th>
                <th style={{ padding: 16 }}>角色</th>
                <th style={{ padding: 16 }}>状态</th>
                <th style={{ padding: 16 }}>创建时间</th>
                <th style={{ padding: 16, textAlign: "right" }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => {
                const isSelf = user.username === currentUsername;
                return (
                  <tr key={user.id} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                    <td style={{ padding: 16, fontWeight: 700 }}>{user.username}{isSelf ? "（当前账号）" : ""}</td>
                    <td style={{ padding: 16 }}>{user.role === "admin" ? "管理员" : user.role === "employee" ? "员工" : "游客"}</td>
                    <td style={{ padding: 16, color: user.is_active ? "#2f9e44" : "#e03131" }}>{user.is_active ? "启用" : "禁用"}</td>
                    <td style={{ padding: 16, color: "var(--text-muted)" }}>{user.created_at ? new Date(user.created_at).toLocaleString() : "--"}</td>
                    <td style={{ padding: 16 }}>
                      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, flexWrap: "wrap" }}>
                        <select
                          value={user.role}
                          disabled={isSelf}
                          onChange={(event) => setRole(user.username, event.target.value as UserRole)}
                          aria-label={`设置 ${user.username} 的角色`}
                          style={{ height: 41, padding: "0 33px 0 15px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-glass)", background: "var(--surface)", color: "var(--text-primary)", opacity: isSelf ? 0.45 : 1 }}
                        >
                          <option value="guest">游客</option>
                          <option value="employee">员工</option>
                          <option value="admin">管理员</option>
                        </select>
                        {user.is_active ? (
                          <button disabled={isSelf} onClick={() => setStatus(user.username, false)} style={{ height: 41, padding: "0 15px", borderRadius: "var(--radius-sm)", background: "rgba(224,49,49,0.12)", color: "#e03131", opacity: isSelf ? 0.45 : 1, display: "flex", alignItems: "center", gap: 7 }}>
                            <UserX size={21} /> 禁用
                          </button>
                        ) : (
                          <button onClick={() => setStatus(user.username, true)} style={{ height: 41, padding: "0 15px", borderRadius: "var(--radius-sm)", background: "rgba(47,158,68,0.12)", color: "#2f9e44", display: "flex", alignItems: "center", gap: 7 }}>
                            <UserCheck size={21} /> 启用
                          </button>
                        )}
                        <button disabled={isSelf} onClick={() => deleteUser(user.username)} style={{ height: 41, padding: "0 15px", borderRadius: "var(--radius-sm)", background: "rgba(224,49,49,0.12)", color: "#e03131", opacity: isSelf ? 0.45 : 1, display: "flex", alignItems: "center", gap: 7 }}>
                          <Trash2 size={21} /> 删除
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!loading && users.length === 0 && <div style={{ padding: 48, textAlign: "center", color: "var(--text-muted)" }}>{activeKeyword ? "没有匹配的用户" : "暂无用户"}</div>}
        </section>
      </main>

      {toast && <div className="toast-container"><div className="toast success" onAnimationEnd={() => window.setTimeout(() => setToast(""), 2500)}>{toast}</div></div>}
    </div>
  );
}
