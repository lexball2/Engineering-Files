import { Dispatch, Fragment, ReactNode, SetStateAction, useEffect, useRef, useState } from "react";
import { Bot, Download, FileText, Image as ImageIcon, Loader2, Send, Sparkles, Trash2, User, X } from "lucide-react";
import type { ChatImage, ChatMessage, ChatSource } from "../App";

interface ChatProps {
  messages: ChatMessage[];
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  loading: boolean;
  setLoading: Dispatch<SetStateAction<boolean>>;
}

interface SourcePreview {
  filename: string;
  content: string;
  total_chars: number;
}

interface QuestionSuggestion {
  identity: string;
  questions: string[];
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "请求失败";
}

function cleanAnswerContent(content: string): string {
  return content
    .replace(/【\s*来源[:：][^】]+】/g, "")
    .replace(/[（(]\s*来源[:：][^)）]+[)）]/g, "")
    .replace(/\s*来源[:：]\s*[^。\n]+/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function shouldShowSources(content: string, sources?: ChatSource[]): boolean {
  if (!sources || sources.length === 0) return false;
  const normalized = content.replace(/\s+/g, "").replace(/[，。！？!?.,;；：:]/g, "");
  const casualStarts = ["你好", "您好", "嗨", "hi", "hello"];
  const casualPhrases = ["请问有什么我可以帮", "有什么可以帮", "我可以帮您", "我可以帮助您"];
  if (normalized.length <= 40 && casualStarts.some((item) => normalized.toLowerCase().startsWith(item))) return false;
  if (casualPhrases.some((item) => normalized.includes(item))) return false;
  return true;
}

function shouldAllowSourcesForQuestion(question: string): boolean {
  const normalized = question
    .replace(/\s+/g, "")
    .replace(/[\u3002\uff0c\uff01\uff1f\uff1b\uff1a,.!?;:]/g, "")
    .toLowerCase();
  if (!normalized) return false;

  const casualExact = [
    "\u4f60\u597d", "\u60a8\u597d", "\u55e8", "hi", "hello", "\u5728\u5417",
    "\u8c22\u8c22", "\u611f\u8c22", "\u65e9\u4e0a\u597d", "\u4e0b\u5348\u597d", "\u665a\u4e0a\u597d",
    "\u4f60\u662f\u8c01", "\u4ecb\u7ecd\u4e00\u4e0b\u4f60\u81ea\u5df1", "\u4f60\u80fd\u505a\u4ec0\u4e48", "\u4f60\u53ef\u4ee5\u505a\u4ec0\u4e48",
  ];
  const generalCues = [
    "\u4ecb\u7ecd\u4f60\u81ea\u5df1", "\u4f60\u5f53\u524d\u4f7f\u7528", "\u4f60\u662f\u4ec0\u4e48\u6a21\u578b",
    "\u4f60\u662f\u4ec0\u4e48", "\u4f60\u80fd\u5e2e\u6211", "\u80fd\u505a\u4ec0\u4e48", "\u5199\u4e00\u6bb5",
    "\u5e2e\u6211\u5199", "\u6da6\u8272", "\u7ffb\u8bd1", "\u6539\u5199", "\u751f\u6210\u6587\u6848", "\u5934\u8111\u98ce\u66b4",
  ];
  const knowledgeCues = [
    "\u77e5\u8bc6\u5e93", "\u6587\u6863", "\u6587\u4ef6", "\u8d44\u6599", "\u62a5\u544a", "\u8bf4\u660e\u4e66",
    "\u5236\u5ea6", "\u6d41\u7a0b", "\u65b9\u6848", "\u5408\u540c", "\u624b\u518c", "\u89c4\u8303",
    "\u8bb0\u5f55", "\u6765\u6e90", "\u5f15\u7528", "\u6839\u636e", "\u4f9d\u636e", "\u7ed3\u5408",
    "\u4e0a\u4f20", "\u603b\u7ed3", "\u8fd9\u4efd", "\u8be5\u6587\u4ef6", "\u8fd9\u7bc7", "\u5185\u5bb9",
    "\u6761\u6b3e", "\u89c4\u5b9a", "\u7528\u6cd5", "\u7981\u5fcc", "\u6ce8\u610f\u4e8b\u9879", "\u6210\u5206",
  ];

  if (casualExact.includes(normalized)) return false;
  if (knowledgeCues.some((cue) => normalized.includes(cue))) return true;
  if (generalCues.some((cue) => normalized.includes(cue))) return false;
  return false;
}

function inferQuestionSuggestions(text: string): QuestionSuggestion | null {
  const normalized = text.replace(/\s+/g, "");
  const isNewEmployee = /新员工|新人|刚入职|刚来|新来的|入职/.test(normalized);
  const mentionsSelf = /我是|本人是|我在|我属于|我来自/.test(normalized);
  if (!isNewEmployee && !mentionsSelf) return null;

  const departmentRules = [
    {
      keys: ["人事", "人力", "hr", "HR"],
      name: "人力资源部新员工",
      questions: ["公司员工手册有哪些重点？", "新员工入职流程是什么？", "员工档案和合同管理流程是什么？", "请总结公司考勤和请假制度。"],
    },
    {
      keys: ["财务", "会计", "出纳"],
      name: "财务部新员工",
      questions: ["公司报销流程和票据要求是什么？", "财务审批权限和流程有哪些？", "月度报表需要参考哪些模板？", "新员工需要了解哪些财务制度？"],
    },
    {
      keys: ["行政", "办公室", "后勤"],
      name: "行政部新员工",
      questions: ["办公用品和固定资产申请流程是什么？", "会议室和接待流程有哪些规定？", "差旅和用车制度是什么？", "行政部门常用表单在哪里？"],
    },
    {
      keys: ["技术", "研发", "开发", "工程", "IT", "it"],
      name: "技术部新员工",
      questions: ["开发环境和账号权限如何申请？", "代码规范和提交流程是什么？", "项目部署和上线流程有哪些？", "技术文档和接口文档在哪里？"],
    },
    {
      keys: ["市场", "新媒体", "运营", "内容"],
      name: "市场/新媒体部新员工",
      questions: ["公司新媒体发布规范是什么？", "图片资产如何检索和下载使用？", "不同平台内容审核流程是什么？", "品牌视觉和文案规范有哪些？"],
    },
    {
      keys: ["销售", "商务", "客户"],
      name: "销售部新员工",
      questions: ["客户跟进和CRM填写规范是什么？", "报价和合同审批流程是什么？", "销售回款流程需要注意什么？", "常用产品资料和话术在哪里？"],
    },
    {
      keys: ["客服", "售后"],
      name: "客服/售后部新员工",
      questions: ["客户问题处理流程是什么？", "常见问题回复话术有哪些？", "投诉升级机制是什么？", "售后记录应该如何填写？"],
    },
  ];

  const matched = departmentRules.find((rule) => rule.keys.some((key) => normalized.includes(key)));
  if (matched) return { identity: matched.name, questions: matched.questions };

  return {
    identity: "新员工",
    questions: [
      "新员工入职需要完成哪些事项？",
      "公司规章制度有哪些重点？",
      "我应该先了解哪些部门流程？",
      "常用文档、制度和模板在哪里查看？",
    ],
  };
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

export default function Chat({ messages, setMessages, loading, setLoading }: ChatProps) {
  const [input, setInput] = useState("");
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [sourcePreview, setSourcePreview] = useState<SourcePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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

  async function previewSource(source: ChatSource) {
    const sourceKey = source.source || source.filename;
    if (!sourceKey || previewLoading) return;
    setPreviewLoading(true);
    try {
      const res = await fetch("/api/chat/source-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        credentials: "same-origin",
        body: JSON.stringify({ source: sourceKey }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `预览失败 (${res.status})`);
      }
      setSourcePreview(await res.json());
    } catch (error) {
      setSourcePreview({
        filename: source.filename,
        content: getErrorMessage(error),
        total_chars: 0,
      });
    } finally {
      setPreviewLoading(false);
    }
  }

  async function send(questionOverride?: string) {
    const q = (questionOverride ?? input).trim();
    if ((!q && !selectedImage) || loading) return;

    const imageToSearch = selectedImage;
    const allowSources = shouldAllowSourcesForQuestion(q);
    const suggestions = inferQuestionSuggestions(q);
    const userText = q || `已上传图片：${imageToSearch?.name || "图片"}`;
    setMessages((prev) => [...prev, { role: "user", content: userText }]);
    const assistant: ChatMessage = { role: "assistant", content: "", sources: [], relatedImages: [], identityGuess: suggestions?.identity, suggestedQuestions: suggestions?.questions };
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
              assistant.sources = allowSources ? JSON.parse(data) as ChatSource[] : [];
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

  function SuggestedQuestionPanel({ identity, questions }: { identity?: string; questions?: string[] }) {
    if (!identity || !questions || questions.length === 0) return null;
    return (
      <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--border-glass)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 9, color: "var(--text-muted)", fontSize: 13 }}>
          <Sparkles size={15} color="var(--primary)" />
          <span>猜你可能是：{identity}</span>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {questions.map((question) => (
            <button
              key={question}
              type="button"
              disabled={loading}
              onClick={() => send(question)}
              style={{
                padding: "8px 11px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-glass)",
                background: "rgba(255,183,125,0.08)",
                color: "var(--text-primary)",
                fontSize: 13,
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.55 : 1,
              }}
            >
              {question}
            </button>
          ))}
        </div>
      </div>
    );
  }

  function Bubble({ role, content, sources, relatedImages, identityGuess, suggestedQuestions, previousUserContent }: ChatMessage & { previousUserContent?: string }) {
    const isUser = role === "user";
    const displayContent = isUser ? content : cleanAnswerContent(content);
    const visibleSources = !isUser && shouldAllowSourcesForQuestion(previousUserContent || "") && shouldShowSources(displayContent, sources) ? sources : [];
    return (
      <div style={{ display: "flex", gap: 14, marginBottom: 29, justifyContent: isUser ? "flex-end" : "flex-start" }}>
        {!isUser && <div style={{ width: 49, height: 49, borderRadius: "var(--radius)", background: "var(--primary-container)", border: "1px solid rgba(255,183,125,0.2)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><Bot size={27} color="var(--primary)" /></div>}
        <div className="chat-message-content" style={{ width: "fit-content", maxWidth: "75%", minWidth: 0 }}>
          <div style={{ padding: "21px 25px", borderRadius: "var(--radius-lg)", ...(isUser ? { background: "var(--chat-user-bubble)", border: "1px solid var(--chat-user-bubble-border)", borderTopRightRadius: 4 } : { background: "var(--surface)", border: "1px solid var(--border-glass)", borderTopLeftRadius: 4 }), wordBreak: "break-word", lineHeight: 1.7 }}>
            <SafeMessage content={displayContent} />
            {!isUser && <ImageResults images={relatedImages} />}
            {!isUser && <SuggestedQuestionPanel identity={identityGuess} questions={suggestedQuestions} />}
          </div>
          {!isUser && visibleSources && visibleSources.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
              {visibleSources.map((source, index) => (
                <button key={`${source.filename}-${index}`} onClick={() => previewSource(source)} title="点击预览来源" style={{ display: "inline-flex", alignItems: "center", gap: 7, maxWidth: 330, padding: "9px 13px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-glass)", background: "rgba(255,255,255,0.04)", color: "var(--text-muted)", fontSize: 18 }}>
                  <FileText size={20} color="var(--primary)" />
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{source.filename}</span>
                </button>
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
        ) : messages.map((message, index) => <Bubble key={index} role={message.role} content={message.content} sources={message.sources} relatedImages={message.relatedImages} identityGuess={message.identityGuess} suggestedQuestions={message.suggestedQuestions} previousUserContent={index > 0 && messages[index - 1].role === "user" ? messages[index - 1].content : ""} />)}
        {loading && <div style={{ display: "flex", gap: 11, alignItems: "center", padding: "15px 0" }}><Loader2 size={25} color="var(--primary)" style={{ animation: "spin 1s linear infinite" }} /><span style={{ fontSize: 20, color: "var(--text-muted)" }}>思考中...</span></div>}
        <div ref={endRef} />
      </div>
      {sourcePreview && (
        <div onClick={() => setSourcePreview(null)} style={{ position: "fixed", inset: 0, zIndex: 1200, background: "rgba(0,0,0,0.46)", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
          <div onClick={(event) => event.stopPropagation()} className="glass-panel" style={{ width: "min(860px, 92vw)", maxHeight: "82vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--border-glass)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
              <div style={{ minWidth: 0 }}>
                <h3 style={{ fontSize: 18, color: "var(--primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{sourcePreview.filename}</h3>
                <span style={{ color: "var(--text-muted)", fontSize: 12 }}>共 {sourcePreview.total_chars.toLocaleString()} 字</span>
              </div>
              <button onClick={() => setSourcePreview(null)} title="关闭" style={{ width: 34, height: 34, borderRadius: "var(--radius-sm)", background: "rgba(255,255,255,0.05)", color: "var(--text-muted)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <X size={17} />
              </button>
            </div>
            <pre style={{ margin: 0, padding: 18, overflow: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word", color: "var(--text-primary)", fontFamily: "var(--font)", fontSize: 13, lineHeight: 1.65 }}>
              {sourcePreview.content}{sourcePreview.total_chars > sourcePreview.content.length ? "\n\n... 内容已截断，仅显示前 2000 字" : ""}
            </pre>
          </div>
        </div>
      )}
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
          <button onClick={() => send()} disabled={loading || (!input.trim() && !selectedImage)} style={{ width: 36, height: 36, borderRadius: "var(--radius-sm)", border: "none", background: loading || (!input.trim() && !selectedImage) ? "var(--text-muted)" : "var(--primary-solid)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, cursor: loading || (!input.trim() && !selectedImage) ? "not-allowed" : "pointer", opacity: loading || (!input.trim() && !selectedImage) ? 0.5 : 1, boxShadow: loading || (!input.trim() && !selectedImage) ? "none" : "0 0 15px var(--primary-glow)", transition: "all 0.2s", alignSelf: "center", padding: 0 }}><Send size={17} /></button>
        </div>
      </div>
    </div>
  );
}
