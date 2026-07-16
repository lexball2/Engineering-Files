import { useState, useEffect } from "react"; import { useNavigate } from "react-router-dom";
import { FileText, MessageSquare, Upload, TrendingUp, Clock, BookOpen, CheckCircle, AlertCircle } from "lucide-react";
import Button from "../components/Button"; import { api } from "../api/client";

interface DocRecord { id:string; filename:string; file_type:string; upload_time:string; status:string }

function timeAgo(dateStr: string): string {
  if (!dateStr) return "--";
  const then = new Date(dateStr).getTime();
  const diff = Date.now() - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
}

export default function Dashboard() {
  const nav = useNavigate();
  const [greeting, setGreeting] = useState("");
  const [docs, setDocs] = useState<DocRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const h = new Date().getHours();
    setGreeting(h < 12 ? "早上好" : h < 18 ? "下午好" : "晚上好");
    api.post("/upload/list")
      .then(r => r.json())
      .then(data => { if (Array.isArray(data)) setDocs(data); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const indexed = docs.filter(d => d.status === "done" || d.status === "indexed").length;
  const stats = [
    { icon: FileText, label: "总文档数", value: docs.length, color: "var(--primary)" },
    { icon: CheckCircle, label: "已索引", value: indexed, color: "#4fc3f7" },
    { icon: AlertCircle, label: "待处理", value: docs.length - indexed, color: "#ffb74d" },
  ];

  const recent = [...docs].sort((a, b) => {
    const da = a.upload_time ? new Date(a.upload_time).getTime() : 0;
    const db = b.upload_time ? new Date(b.upload_time).getTime() : 0;
    return db - da;
  }).slice(0, 5);

  return (
    <div className="page-frame" style={{ height: "100vh", overflowY: "auto", background: "var(--body-gradient)" }}>
      <div className="page-content dashboard-content">
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: 39, fontWeight: 700, color: "var(--text-primary)" }}>
            {greeting}，{localStorage.getItem("username") || "用户"}
          </h1>
          <p style={{ fontSize: 20, color: "var(--text-muted)", marginTop: 9 }}>
            欢迎回到企业智能知识库。向知识库提问、上传新的文档，或浏览已有资料。
          </p>
        </div>

        <div className="dashboard-stats">
          {stats.map(({ icon: Icon, label, value, color }) => (
            <div key={label} className="glass-panel" style={{ padding: 25, borderRadius: "var(--radius-lg)" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                <span style={{ fontSize: 18, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0 }}>{label}</span>
                <div style={{ padding: 13, borderRadius: "var(--radius-sm)", background: `${color}15` }}>
                  <Icon size={27} color={color} />
                </div>
              </div>
              <div style={{ fontSize: 39, fontWeight: 700, color: "var(--text-primary)" }}>
                {loading ? "..." : value.toLocaleString()}
              </div>
            </div>
          ))}
        </div>

        <div className="dashboard-grid">
          <div className="glass-panel" style={{ padding: 29, borderRadius: "var(--radius-lg)" }}>
            <h3 style={{ fontSize: 22, fontWeight: 700, marginBottom: 23, display: "flex", alignItems: "center", gap: 9 }}>
              <TrendingUp size={25} color="var(--primary)" />快捷入口
            </h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <Button variant="secondary" onClick={() => nav("/chat")} style={{ justifyContent: "flex-start", width: "100%" }}>
                <MessageSquare size={23} />知识问答
              </Button>
              <Button variant="secondary" onClick={() => nav("/documents")} style={{ justifyContent: "flex-start", width: "100%" }}>
                <Upload size={23} />上传文档
              </Button>
              <Button variant="secondary" onClick={() => nav("/documents")} style={{ justifyContent: "flex-start", width: "100%" }}>
                <BookOpen size={23} />浏览知识库
              </Button>
            </div>
          </div>

          <div className="glass-panel" style={{ padding: 29, borderRadius: "var(--radius-lg)" }}>
            <h3 style={{ fontSize: 22, fontWeight: 700, marginBottom: 23, display: "flex", alignItems: "center", gap: 9 }}>
              <Clock size={25} color="var(--primary)" />最近上传
            </h3>
            {loading ? (
              <div style={{ padding: "25px 0", textAlign: "center", color: "var(--text-muted)", fontSize: 20 }}>加载中...</div>
            ) : recent.length === 0 ? (
              <div style={{ padding: "25px 0", textAlign: "center", color: "var(--text-muted)", fontSize: 20 }}>
                暂无文档，前往<Button variant="ghost" size="sm" onClick={() => nav("/documents")}>文档管理</Button>上传
              </div>
            ) : (
              recent.map((doc, i) => (
                <div key={doc.id || i} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "12px 0", borderBottom: i < recent.length - 1 ? "1px solid var(--border-glass)" : "none" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
                    <FileText size={21} color="var(--text-muted)" style={{ flexShrink: 0 }} />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 20, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{doc.filename}</div>
                      <div style={{ fontSize: 18, color: "var(--text-muted)", marginTop: 2 }}>{doc.file_type?.toUpperCase() || "FILE"}</div>
                    </div>
                  </div>
                  <span style={{ fontSize: 18, color: "var(--text-muted)", whiteSpace: "nowrap", flexShrink: 0, marginLeft: 12 }}>{timeAgo(doc.upload_time)}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
