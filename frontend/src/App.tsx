import { SetStateAction, useCallback, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Chat from "./pages/Chat";
import Documents from "./pages/Documents";
import ImageAssets from "./pages/ImageAssets";
import Login from "./pages/Login";
import AdminUsers from "./pages/AdminUsers";
import type { UserRole } from "./api/auth";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: ChatSource[];
  relatedImages?: ChatImage[];
}

export interface ChatSource {
  filename: string;
  source?: string;
  score?: string;
}

export interface ChatImage {
  id: string;
  filename: string;
  thumbnail_url: string;
  view_url: string;
  download_count: number;
  hot_score?: number;
  score?: number;
}

const CHAT_MESSAGES_KEY = "kb-chat-messages";
const MAX_CHAT_ROUNDS = 6;
const MAX_CHAT_MESSAGES = MAX_CHAT_ROUNDS * 2;

function trimChatMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages.slice(-MAX_CHAT_MESSAGES);
}

function loadChatMessages(): ChatMessage[] {
  try {
    const saved = localStorage.getItem(CHAT_MESSAGES_KEY);
    if (!saved) return [];
    const parsed = JSON.parse(saved);
    if (!Array.isArray(parsed)) return [];
    return trimChatMessages(parsed.filter(
      (item): item is ChatMessage =>
        item &&
        (item.role === "user" || item.role === "assistant") &&
        typeof item.content === "string",
    ));
  } catch {
    return [];
  }
}

function normalizeRole(role: string | null): UserRole {
  if (role === "admin" || role === "employee" || role === "guest") return role;
  return role === "user" ? "employee" : "guest";
}

function ProtectedLayout({ onLogout, role }: { onLogout: () => void; role: UserRole }) {
  const [collapsed, setCollapsed] = useState(false);
  const [compactViewport, setCompactViewport] = useState(() => window.matchMedia("(max-width: 900px)").matches);
  const [lightMode, setLightMode] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(loadChatMessages);
  const isStaff = role === "employee" || role === "admin";

  const setLimitedChatMessages = useCallback((value: SetStateAction<ChatMessage[]>) => {
    setChatMessages((prev) => {
      const next = typeof value === "function" ? value(prev) : value;
      return trimChatMessages(next);
    });
  }, []);

  useEffect(() => {
    const stored = localStorage.getItem("kb-lightMode");
    if (stored === "true") {
      setLightMode(true);
      document.documentElement.classList.add("light");
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(CHAT_MESSAGES_KEY, JSON.stringify(trimChatMessages(chatMessages)));
  }, [chatMessages]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 900px)");
    const updateViewport = () => setCompactViewport(media.matches);
    media.addEventListener("change", updateViewport);
    return () => media.removeEventListener("change", updateViewport);
  }, []);

  function toggleTheme() {
    const next = !lightMode;
    setLightMode(next);
    localStorage.setItem("kb-lightMode", String(next));
    if (next) document.documentElement.classList.add("light");
    else document.documentElement.classList.remove("light");
  }

  const sidebarCollapsed = collapsed || compactViewport;
  const ml = sidebarCollapsed ? 52 : 220;

  return (
    <>
      <Sidebar
        username={localStorage.getItem("username") || "用户"}
        role={role}
        onLogout={onLogout}
        collapsed={sidebarCollapsed}
        collapseLocked={compactViewport}
        onToggleCollapse={() => setCollapsed(!collapsed)}
        lightMode={lightMode}
        onToggleTheme={toggleTheme}
      />
      <div className={`app-main${sidebarCollapsed ? " content-expanded" : ""}`} style={{ marginLeft: ml, transition: "margin-left 0.25s" }}>
        <Routes>
          <Route path="/dashboard" element={isStaff ? <Dashboard /> : <Navigate to="/chat" replace />} />
          <Route path="/chat" element={<Chat messages={chatMessages} setMessages={setLimitedChatMessages} />} />
          <Route path="/documents" element={isStaff ? <Documents /> : <Navigate to="/chat" replace />} />
          <Route path="/image-assets" element={isStaff ? <ImageAssets /> : <Navigate to="/chat" replace />} />
          <Route path="/admin/users" element={role === "admin" ? <AdminUsers /> : <Navigate to={isStaff ? "/dashboard" : "/chat"} replace />} />
          <Route path="*" element={<Navigate to={isStaff ? "/dashboard" : "/chat"} replace />} />
        </Routes>
      </div>
    </>
  );
}

export default function App() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [role, setRole] = useState<UserRole>(() => normalizeRole(localStorage.getItem("role")));

  useEffect(() => {
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((user) => {
        if (!user?.role) throw new Error("invalid session");
        const latestRole = normalizeRole(user.role);
        localStorage.removeItem("token");
        localStorage.setItem("username", user.username || "用户");
        localStorage.setItem("role", latestRole);
        setRole(latestRole);
        setLoggedIn(true);
      })
      .catch(() => {
        ["token", "username", "role", "session_id", CHAT_MESSAGES_KEY].forEach((key) => localStorage.removeItem(key));
        setLoggedIn(false);
      })
      .finally(() => setAuthChecked(true));
  }, []);

  useEffect(() => {
    const expire = () => {
      ["token", "username", "role", "session_id", CHAT_MESSAGES_KEY].forEach((key) => localStorage.removeItem(key));
      setRole("guest");
      setLoggedIn(false);
    };
    window.addEventListener("auth-expired", expire);
    return () => window.removeEventListener("auth-expired", expire);
  }, []);

  function logout() {
    fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }).catch(() => {});
    ["token", "username", "role", "session_id", CHAT_MESSAGES_KEY].forEach((key) => localStorage.removeItem(key));
    setRole("guest");
    setLoggedIn(false);
  }

  return (
    <BrowserRouter>
      {!authChecked ? null : !loggedIn ? (
        <Login onLogin={(username, nextRole) => { localStorage.setItem("username", username); localStorage.setItem("role", nextRole); setRole(nextRole); setLoggedIn(true); }} />
      ) : (
        <ProtectedLayout onLogout={logout} role={role} />
      )}
    </BrowserRouter>
  );
}
