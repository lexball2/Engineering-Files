import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, LogIn, UserRound } from "lucide-react";

import { authApi } from "../api/auth";
import type { UserRole } from "../api/auth";

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "请求失败";
}

export default function Login({ onLogin }: { onLogin: (u: string, role: UserRole) => void }) {
  const [tab, setTab] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [guestLoading, setGuestLoading] = useState(false);
  const nav = useNavigate();

  const inputStyle: React.CSSProperties = {
    width: "100%",
    height: 63,
    padding: "0 21px",
    borderRadius: "var(--radius)",
    border: "1px solid var(--border-glass)",
    fontSize: 20,
    outline: "none",
    background: "#fff",
    color: "#1a1a2e",
    fontFamily: "inherit",
    transition: "border 0.2s",
  };

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setUsername("");
      setPassword("");
      setConfirm("");
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  function finishLogin(data: { username: string; role: UserRole }) {
    localStorage.removeItem("token");
    localStorage.setItem("role", data.role);
    onLogin(data.username, data.role);
    nav(data.role === "guest" ? "/chat" : "/dashboard");
  }

  async function submit() {
    setError("");
    if (!username.trim() || !password) {
      setError("请填写完整信息");
      return;
    }
    if (tab === "register" && password !== confirm) {
      setError("两次密码不一致");
      return;
    }
    if (tab === "register" && password.length < 8) {
      setError("密码至少8位");
      return;
    }
    setLoading(true);
    try {
      const fn = tab === "login" ? authApi.login : authApi.register;
      finishLogin(await fn(username, password));
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  async function loginAsGuest() {
    setError("");
    setGuestLoading(true);
    try {
      finishLogin(await authApi.guestLogin());
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setGuestLoading(false);
    }
  }

  const tabs: [string, string][] = [["login", "登录"], ["register", "注册"]];

  return (
    <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--body-gradient)", position: "relative", overflow: "hidden" }}>
      <div style={{ position: "absolute", top: "20%", left: "10%", width: 400, height: 400, borderRadius: "50%", background: "radial-gradient(circle, rgba(255,183,125,0.08) 0%, transparent 70%)", filter: "blur(80px)" }} />
      <div style={{ position: "absolute", bottom: "20%", right: "10%", width: 500, height: 500, borderRadius: "50%", background: "radial-gradient(circle, rgba(2,151,232,0.06) 0%, transparent 70%)", filter: "blur(100px)" }} />
      <div style={{ position: "relative", zIndex: 10, width: "min(510px, calc(100vw - 32px))" }}>
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div style={{ width: 73, height: 73, borderRadius: "var(--radius)", background: "var(--primary-container)", border: "1px solid rgba(255,183,125,0.2)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 18px", backdropFilter: "blur(8px)" }}>
            <LogIn size={39} color="var(--primary)" />
          </div>
          <h1 style={{ fontSize: 31, fontWeight: 700, color: "var(--primary)" }}>企业智能知识库</h1>
          <p style={{ fontSize: 20, color: "var(--text-muted)", marginTop: 8 }}>游客可直接进入智能问答，员工登录后可使用管理功能</p>
        </div>
        <div className="glass-panel" style={{ padding: "32px 28px" }}>
          <div style={{ display: "flex", borderBottom: "1px solid var(--border-subtle)", marginBottom: 24 }}>
            {tabs.map(([key, label]) => (
              <button
                key={key}
                onClick={() => setTab(key as "login" | "register")}
                style={{
                  flex: 1,
                  padding: "14px 0",
                  border: "none",
                  background: "none",
                  fontSize: 21,
                  fontWeight: tab === key ? 600 : 400,
                  color: tab === key ? "var(--primary)" : "var(--text-muted)",
                  borderBottom: tab === key ? "2px solid var(--primary)" : "2px solid transparent",
                  transition: "all 0.2s",
                  cursor: "pointer",
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <input style={inputStyle} name="kb-login-user" autoComplete="off" placeholder="用户名 / 企业邮箱" value={username} onChange={(event) => setUsername(event.target.value)} onKeyDown={(event) => event.key === "Enter" && submit()} onFocus={(event) => { event.target.style.borderColor = "var(--primary)"; }} onBlur={(event) => { event.target.style.borderColor = "var(--border-glass)"; }} />
            <input style={inputStyle} name="kb-login-password" autoComplete="new-password" type="password" placeholder="请输入密码" value={password} onChange={(event) => setPassword(event.target.value)} onKeyDown={(event) => event.key === "Enter" && submit()} onFocus={(event) => { event.target.style.borderColor = "var(--primary)"; }} onBlur={(event) => { event.target.style.borderColor = "var(--border-glass)"; }} />
            {tab === "register" && <input style={inputStyle} name="kb-confirm-password" autoComplete="new-password" type="password" placeholder="确认密码" value={confirm} onChange={(event) => setConfirm(event.target.value)} onKeyDown={(event) => event.key === "Enter" && submit()} onFocus={(event) => { event.target.style.borderColor = "var(--primary)"; }} onBlur={(event) => { event.target.style.borderColor = "var(--border-glass)"; }} />}
            {error && <div style={{ fontSize: 19, color: "#ff4d4f", padding: "4px 0" }}>{error}</div>}
            <button onClick={submit} disabled={loading || guestLoading} style={{ width: "100%", height: 63, borderRadius: "var(--radius)", border: "none", background: "var(--primary-solid)", color: "#fff", fontSize: 21, fontWeight: 600, marginTop: 4, cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.7 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 9, boxShadow: "0 0 20px var(--primary-glow)", transition: "all 0.2s" }}>
              {loading && <Loader2 size={18} style={{ animation: "spin 1s linear infinite" }} />}{loading ? "处理中..." : tab === "login" ? "立即登录" : "创建账户"}
            </button>
            <button onClick={loginAsGuest} disabled={loading || guestLoading} style={{ width: "100%", height: 57, borderRadius: "var(--radius)", border: "1px solid var(--border-glass)", background: "var(--primary-container)", color: "var(--primary)", fontSize: 20, fontWeight: 700, cursor: guestLoading ? "not-allowed" : "pointer", opacity: guestLoading ? 0.7 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 9 }}>
              {guestLoading ? <Loader2 size={18} style={{ animation: "spin 1s linear infinite" }} /> : <UserRound size={21} />}
              {guestLoading ? "进入中..." : "游客登录，仅使用智能问答"}
            </button>
          </div>
        </div>
        <p style={{ textAlign: "center", fontSize: 18, color: "var(--text-muted)", marginTop: 20, letterSpacing: 0, textTransform: "uppercase" }}>Protected by Insight Engine Security Hub</p>
      </div>
    </div>
  );
}
