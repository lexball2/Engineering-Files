import { Dispatch, Fragment, ReactNode, SetStateAction, useEffect, useRef, useState } from "react";
import { Bot, Download, FileText, Image as ImageIcon, Loader2, Send, Sparkles, Trash2, User, X } from "lucide-react";
import type { ChatImage, ChatMessage, ChatSource } from "../App";

interface ChatProps {
  messages: ChatMessage[];
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "请求失败";
}

function renderInline(text: string): ReactNode[] {
  return text.split(/(\*\*.+?\*\*|`.+?`)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
    return <Fragment key={index}>{part}</Fragment>;
  });
}

function SafeMessage({ content }: { content: string }) {
  const lines = content.split("\n");
  return <>{lines.map((line, index) => <Fragment key={index}>{renderInline(line)}{index < lines.length - 1 && <br />}</Fragment>)}</>;
}

function authHeaders(): Record<string, string> {
  return {};
}

async function searchByImage(file: File, signal?: AbortSignal): Promise<ChatImage[]> {
  const form = new FormData();
  form.append("file", file);
  form.append("limit", "6");
  const res = await fetch("/api/images/search/image", { method: "POST", headers: authHeaders(), credentials: "same-origin", body: form, signal });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `图片检索失败 (${res.status})`);
  }
  return res.json();
}

async function understandImage(file: File, question: string, signal?: AbortSignal): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  form.append("question", question || "请识别这张图片的主要内容，它是否来自某个游戏、影视或品牌？");
  const res = await fetch("/api/images/understand", { method: "POST", headers: authHeaders(), credentials: "same-origin", body: form, signal });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `图片识别失败 (${res.status})`);
  }
  const data = await res.json();
  return data.answer || "";
}

async function downloadImage(image: ChatImage) {
  const res = await fetch("/api/images/download", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    credentials: "same-origin",
    body: JSON.stringify({ id: image.id }),
  });
  if (!res.ok) throw new Error("图片下载失败");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = image.filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export default function Chat({ messages, setMessages }: ChatProps) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function clearHistory() {
    const sid = localStorage.getItem("session_id");
    try {
      if (sid) await fetch("/api/chat/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ session_id: sid }),
      });
    } finally {
      localStorage.removeItem("session_id");
      setSelectedImage(null);
      setInput("");
      setMessages([]);
    }
  }

  async function send() {
    const q = input.trim();
    if ((!q && !selectedImage) || loading) return;

    const imageToSearch = selectedImage;
    const userText = q || `已上传图片：${imageToSearch?.name || "图片"}`;
    setMessages((prev) => [...prev, { role: "user", content: userText }]);
    const assistant: ChatMessage = { role: "assistant", content: "", sources: [], relatedImages: [] };
    setMessages((prev) => [...prev, assistant]);
    setInput("");
    setSelectedImage(null);
    setLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      if (imageToSearch) {
        const [images, answer] = await Promise.all([
          searchByImage(imageToSearch, controller.signal).catch(() => []),
          understandImage(imageToSearch, q, controller.signal),
        ]);
        assistant.relatedImages = images;
        assistant.content = answer || "已识别图片，但模型没有返回明确描述。";
        setMessages((prev) => {
          const copy = [...prev];
          copy[copy.length - 1] = { ...assistant };
          return copy;
        });
        return;
      }

      const sid = localStorage.getItem("session_id") || `sid_${crypto.randomUUID().replace(/-/g, "")}`;
      localStorage.setItem("session_id", sid);
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ question: q, session_id: sid }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`请求失败 (${res.status})`);
      const reader = res.body?.getReader();
      if (!reader) throw new Error("响应内容为空");

      const decoder = new TextDecoder();
      let buf = "";
      let eventName = "message";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() || "";

        for (const rawLine of lines) {
          const line = rawLine.trimEnd();
          if (line.startsWith("event: ")) {
            eventName = line.slice(7).trim();
            continue;
          }
          if (!line.startsWith("data: ")) continue;

          const data = line.slice(6);
          if (eventName === "sources") {
            try {
              assistant.sources = JSON.parse(data) as ChatSource[];
            } catch {
              assistant.sources = [];
            }
          } else if (eventName === "related_images") {
            try {
              const images = JSON.parse(data) as ChatImage[];
              assistant.relatedImages = [...(assistant.relatedImages || []), ...images].filter((img, index, all) => all.findIndex((x) => x.id === img.id) === index);
            } catch {
              assistant.relatedImages = assistant.relatedImages || [];
            }
          } else if (eventName === "chunk" || eventName === "error") {
            try {
              assistant.content += JSON.parse(data) as string;
            } catch {
              assistant.content += data;
            }
          } else if (eventName === "done") {
            eventName = "message";
            continue;
          }
          eventName = "message";

          setMessages((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = { ...assistant };
            return copy;
          });
        }
      }
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setMessages((prev) => [...prev.slice(0, -1), { role: "assistant", content: `错误: ${getErrorMessage(error)}` }]);
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setLoading(false);
    }
  }

  function ImageResults({ images }: { images?: ChatImage[] }) {
    if (!images || images.length === 0) return null;
    return (
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 10, marginTop: 12 }}>
        {images.map((image) => (
          <div key={image.id} style={{ border: "1px solid var(--border-glass)", borderRadius: "var(--radius)", overflow: "hidden", background: "rgba(255,255,255,0.04)" }}>
            <img src={image.thumbnail_url} alt={image.filename} style={{ width: "100%", aspectRatio: "4/3", objectFit: "cover", display: "block" }} />
            <div style={{ padding: 8 }}>
              <div title={image.filename} style={{ fontSize: 18, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{image.filename}</div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 7, fontSize: 17, color: "var(--text-muted)" }}>
                <span>下载 {image.download_count}</span>
                <button onClick={() => downloadImage(image)} title="下载图片" style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", padding: 5, display: "flex" }}><Download size={18} /></button>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  function Bubble({ role, content, sources, relatedImages }: ChatMessage) {
    const isUser = role === "user";
    const visibleSources = sources;
    return (
      <div style={{ display: "flex", gap: 14, marginBottom: 29, justifyContent: isUser ? "flex-end" : "flex-start" }}>
        {!isUser && <div style={{ width: 49, height: 49, borderRadius: "var(--radius)", background: "var(--primary-container)", border: "1px solid rgba(255,183,125,0.2)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><Bot size={27} color="var(--primary)" /></div>}
        <div className="chat-message-content" style={{ width: "fit-content", maxWidth: "75%", minWidth: 0 }}>
          <div style={{ padding: "21px 25px", borderRadius: "var(--radius-lg)", ...(isUser ? { background: "var(--chat-user-bubble)", border: "1px solid var(--chat-user-bubble-border)", borderTopRightRadius: 4 } : { background: "var(--surface)", border: "1px solid var(--border-glass)", borderTopLeftRadius: 4 }), wordBreak: "break-word", lineHeight: 1.7 }}>
            <SafeMessage content={content} />
            {!isUser && <ImageResults images={relatedImages} />}
          </div>
          {!isUser && visibleSources && visibleSources.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
              {visibleSources.map((source, index) => (
                <span key={`${source.filename}-${index}`} title={source.source || source.filename} style={{ display: "inline-flex", alignItems: "center", gap: 7, maxWidth: 330, padding: "9px 13px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-glass)", background: "rgba(255,255,255,0.04)", color: "var(--text-muted)", fontSize: 18 }}>
                  <FileText size={20} color="var(--primary)" />
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{source.filename}</span>
                </span>
              ))}
            </div>
          )}
        </div>
        {isUser && <div style={{ width: 49, height: 49, borderRadius: "var(--radius)", background: "var(--chat-user-avatar)", border: "1px solid var(--chat-user-bubble-border)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><User size={27} color="var(--chat-user-icon)" /></div>}
      </div>
    );
  }

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: "var(--body-gradient)" }}>
      <header className="glass-nav page-header" style={{ height: 73, display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, zIndex: 40 }}>
        <h2 style={{ fontSize: 22, fontWeight: 700, color: "var(--primary)", display: "flex", alignItems: "center", gap: 9 }}><Sparkles size={25} />知识问答</h2>
        <button onClick={clearHistory} disabled={loading || messages.length === 0} title="清理记录" style={{ height: 45, display: "flex", alignItems: "center", gap: 9, padding: "0 17px", borderRadius: "var(--radius-sm)", background: "rgba(255,255,255,0.04)", color: "var(--text-muted)", opacity: loading || messages.length === 0 ? 0.45 : 1 }}>
          <Trash2 size={22} />
          <span style={{ fontSize: 19 }}>清理记录</span>
        </button>
      </header>
      <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px", display: "flex", flexDirection: "column" }}>
        {messages.length === 0 ? (
          <div className="chat-empty-state" style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "32px 0", textAlign: "center" }}>
            <Sparkles size={73} color="var(--primary)" style={{ opacity: 0.8, marginBottom: 26 }} />
            <h3 style={{ fontSize: 31, fontWeight: 700, marginBottom: 14 }}>向知识库提问</h3>
            <p style={{ fontSize: 21, color: "var(--text-muted)", lineHeight: 1.6 }}>可以输入问题，也可以附加图片，让系统识别图片内容并检索相关图片。</p>
          </div>
        ) : messages.map((message, index) => <Bubble key={index} role={message.role} content={message.content} sources={message.sources} relatedImages={message.relatedImages} />)}
        {loading && <div style={{ display: "flex", gap: 11, alignItems: "center", padding: "15px 0" }}><Loader2 size={25} color="var(--primary)" style={{ animation: "spin 1s linear infinite" }} /><span style={{ fontSize: 20, color: "var(--text-muted)" }}>思考中...</span></div>}
        <div ref={endRef} />
      </div>
      <div style={{ padding: "0 24px 10px" }}>
        {selectedImage && (
          <div className="chat-compose" style={{ marginBottom: 6, display: "flex", alignItems: "center", gap: 7, color: "var(--text-muted)", fontSize: 12 }}>
            <ImageIcon size={16} color="var(--primary)" />
            <span>{selectedImage.name}</span>
            <button onClick={() => setSelectedImage(null)} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}><X size={16} /></button>
          </div>
        )}
        <div className="glass-panel chat-compose" style={{ padding: "4px 8px", minHeight: 40, display: "flex", alignItems: "center", gap: 6, border: "1px solid rgba(255,183,125,0.1)", boxShadow: "0 0 20px var(--primary-glow)" }}>
          <input id="chat-image-input" type="file" accept="image/*" hidden onChange={(event) => setSelectedImage(event.target.files?.[0] || null)} />
          <button onClick={() => document.getElementById("chat-image-input")?.click()} title="上传图片识别" style={{ width: 34, height: 34, borderRadius: "var(--radius-sm)", border: "none", background: "rgba(255,255,255,0.04)", color: "var(--text-muted)", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flexShrink: 0, alignSelf: "center", padding: 0 }}><ImageIcon size={17} /></button>
          <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="输入您的问题..." onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(); } }}
            style={{ flex: 1, minHeight: 34, height: 34, border: "none", outline: "none", resize: "none", background: "transparent", color: "var(--text-primary)", fontSize: 12, fontFamily: "inherit", lineHeight: "18px", padding: "8px 0", overflowY: "auto" }} />
          <button onClick={send} disabled={loading || (!input.trim() && !selectedImage)} style={{ width: 36, height: 36, borderRadius: "var(--radius-sm)", border: "none", background: loading || (!input.trim() && !selectedImage) ? "var(--text-muted)" : "var(--primary-solid)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, cursor: loading || (!input.trim() && !selectedImage) ? "not-allowed" : "pointer", opacity: loading || (!input.trim() && !selectedImage) ? 0.5 : 1, boxShadow: loading || (!input.trim() && !selectedImage) ? "none" : "0 0 15px var(--primary-glow)", transition: "all 0.2s", alignSelf: "center", padding: 0 }}><Send size={17} /></button>
        </div>
      </div>
    </div>
  );
}
