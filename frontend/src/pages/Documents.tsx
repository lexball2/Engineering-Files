import { useState, useEffect } from "react";
import { Upload, FileText, CheckCircle, Database, Search, Filter, Eye, Download, Trash2, Image as ImageIcon, Flame } from "lucide-react";
import { api } from "../api/client";

interface DocRecord { id:string; filename:string; file_type:string; upload_time:string; status:string }
interface ImageRecord {
  id: string;
  filename: string;
  width: number;
  height: number;
  file_size: number;
  download_count: number;
  hot_score: number;
  created_at: string;
  thumbnail_url: string;
  view_url: string;
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "请求失败";
}

const TOAST_DURATION_MS = 7000;

export default function Documents() {
  const isAdmin = localStorage.getItem("role") === "admin";
  const [toast, setToast] = useState<{msg:string;error?:boolean}|null>(null);
  const [docs, setDocs] = useState<DocRecord[]>([]);
  const [images, setImages] = useState<ImageRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [imageLoading, setImageLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [preview, setPreview] = useState<{filename:string;content:string;total:number}|null>(null);

  async function fetchDocs(){ try{ setLoading(true); const r=await api.post("/upload/list").catch(()=>null); if(r) setDocs(await r.json()); }catch{ setDocs([]); }finally{setLoading(false)} }
  async function fetchImages(){ try{ setImageLoading(true); const r=await api.post("/images/list").catch(()=>null); if(r) setImages(await r.json()); }catch{ setImages([]); }finally{setImageLoading(false)} }
  useEffect(()=>{fetchDocs(); fetchImages()},[]);

  async function handleUpload(f:File){ try{ await api.upload("/upload",f); setToast({msg:`${f.name} 上传成功 — 已加入知识库`}); fetchDocs(); }catch(e:unknown){setToast({msg:getErrorMessage(e),error:true})} setTimeout(()=>setToast(null),TOAST_DURATION_MS) }

  async function handleImageUpload(f: File) {
    try {
      await api.upload("/images/upload", f);
      setToast({ msg: `${f.name} 上传成功 — 已加入图片库` });
      fetchImages();
    } catch (e: unknown) {
      setToast({ msg: getErrorMessage(e), error: true });
    }
    setTimeout(() => setToast(null), TOAST_DURATION_MS);
  }

  const handlePreview = async (doc: DocRecord) => {
    try { const r = await api.post("/upload/preview", { id: doc.id }); const d = await r.json(); setPreview({ filename: d.filename, content: d.content, total: d.total_chars }); }
    catch (e: unknown) { setToast({ msg: getErrorMessage(e), error: true }); setTimeout(() => setToast(null), TOAST_DURATION_MS); }
  };

  const handleDownload = async (doc: DocRecord) => {
    try {
      const res = await fetch("/api/upload/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ id: doc.id }),
      });
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = doc.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setToast({ msg: getErrorMessage(e), error: true });
      setTimeout(() => setToast(null), TOAST_DURATION_MS);
    }
  };

  const handleDelete = async (doc: DocRecord) => {
    if (!confirm(`确认删除 "${doc.filename}"？此操作同时清理向量库数据。`)) return;
    try { await api.post("/upload/delete", { id: doc.id }); setToast({ msg: `${doc.filename} 已删除` }); setTimeout(() => setToast(null), TOAST_DURATION_MS); fetchDocs(); }
    catch (e: unknown) { setToast({ msg: getErrorMessage(e), error: true }); setTimeout(() => setToast(null), TOAST_DURATION_MS); }
  };

  const handleImageDownload = async (image: ImageRecord) => {
    try {
      const res = await fetch("/api/images/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ id: image.id }),
      });
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = image.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      fetchImages();
    } catch (e: unknown) {
      setToast({ msg: getErrorMessage(e), error: true });
      setTimeout(() => setToast(null), TOAST_DURATION_MS);
    }
  };

  const handleImageDelete = async (image: ImageRecord) => {
    if (!confirm(`确认删除 "${image.filename}"？此操作同时清理图片向量数据。`)) return;
    try {
      await api.post("/images/delete", { id: image.id });
      setToast({ msg: `${image.filename} 已删除` });
      setTimeout(() => setToast(null), TOAST_DURATION_MS);
      fetchImages();
    } catch (e: unknown) {
      setToast({ msg: getErrorMessage(e), error: true });
      setTimeout(() => setToast(null), TOAST_DURATION_MS);
    }
  };

  const filtered = docs.filter(d=>!search||d.filename.toLowerCase().includes(search.toLowerCase()));
  const stats = [{label:"文件总数",value:docs.length,color:"var(--primary)",icon:FileText},{label:"已索引",value:docs.filter(d=>d.status==="done"||d.status==="indexed").length,color:"#4fc3f7",icon:CheckCircle},{label:"处理中",value:docs.filter(d=>d.status!=="done"&&d.status!=="indexed").length,color:"#81c784",icon:Upload}];

  return (
    <div style={{ height:"100vh", display:"flex", flexDirection:"column", background:"var(--body-gradient)" }}>
      <header className="glass-nav page-header" style={{ height:73, display:"flex", alignItems:"center", position:"sticky", top:0, zIndex:40 }}>
        <h2 style={{ fontSize:22, fontWeight:700, color:"var(--primary)", display:"flex", alignItems:"center", gap:9 }}><Database size={25}/>文档管理</h2>
      </header>
      <div className="page-frame" style={{ flex:1, overflowY:"auto" }}>
        <div className="page-content">
          <div className="glass-panel" style={{ padding:32, borderRadius:"var(--radius-lg)", marginBottom:20, textAlign:"center", cursor:"pointer", border:"2px dashed rgba(255,183,125,0.2)", transition:"all 0.3s" }}
            onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();const f=e.dataTransfer.files[0];if(f)handleUpload(f)}} onClick={()=>document.getElementById("file-input")?.click()}>
            <input id="file-input" type="file" hidden accept=".txt,.md,.docx,.pdf,.xlsx,.pptx" onChange={e=>{const f=e.target.files?.[0];if(f)handleUpload(f)}}/>
            <div style={{ width:73, height:73, borderRadius:"50%", background:"var(--primary-container)", display:"flex", alignItems:"center", justifyContent:"center", margin:"0 auto 18px" }}><Upload size={35} color="var(--primary)"/></div>
            <h3 style={{ fontSize:25, fontWeight:700, marginBottom:10 }}>点击或拖拽文件至此处上传</h3>
            <p style={{ fontSize:19, color:"var(--text-muted)" }}>支持 PDF、Markdown、TXT 或 Word 文档。最大单文件限制 20MB。系统将自动进行向量化索引。</p>
          </div>
          <div className="document-stats">
            {stats.map(({label,value,color,icon:Icon})=>(
              <div key={label} className="glass-panel" style={{ padding:20, borderRadius:"var(--radius)", display:"flex", alignItems:"center", gap:16 }}>
                <div style={{ padding:14, borderRadius:"var(--radius-sm)", background:`${color}15` }}><Icon size={27} color={color}/></div>
                <div><p style={{ fontSize:17, fontWeight:600, color:"var(--text-muted)", textTransform:"uppercase", letterSpacing:0 }}>{label}</p><p style={{ fontSize:31, fontWeight:700, color:"var(--text-primary)" }}>{value}</p></div>
              </div>
            ))}
          </div>
          <div className="glass-panel" style={{ borderRadius:"var(--radius-lg)", overflow:"hidden" }}>
            <div className="document-list-toolbar" style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"16px 24px", borderBottom:"1px solid var(--border-subtle)" }}>
              <h3 style={{ fontSize:22, fontWeight:700 }}>最近上传</h3>
              <div className="document-search-controls" style={{ display:"flex", gap:8, alignItems:"center" }}>
                <div className="document-search-box" style={{ display:"flex", alignItems:"center", gap:8, padding:"8px 14px", borderRadius:"var(--radius-sm)", background:"rgba(255,255,255,0.03)", border:"1px solid var(--border-glass)" }}>
                  <Search size={21} color="var(--text-muted)"/><input placeholder="搜索文件名..." value={search} onChange={e=>setSearch(e.target.value)} style={{ background:"none", border:"none", outline:"none", color:"var(--text-primary)", fontSize:19, width:210 }}/>
                </div>
                <button style={{ padding:8, borderRadius:"var(--radius-sm)", color:"var(--text-muted)", background:"none" }}><Filter size={16}/></button>
              </div>
            </div>
            {loading?<div style={{ padding:"40px", textAlign:"center", color:"var(--text-muted)" }}>加载中...</div>:filtered.length===0?<div style={{ padding:"60px", textAlign:"center", color:"var(--text-muted)" }}><FileText size={40} style={{ opacity:0.3, marginBottom:12 }}/><p>暂无文档</p></div>:filtered.map((doc,i)=>(
              <div key={doc.id||i} className="document-row" style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"16px 24px", borderBottom:i<filtered.length-1?"1px solid var(--border-glass)":"none", transition:"background 0.2s" }}
                onMouseEnter={e=>e.currentTarget.style.background="rgba(255,255,255,0.02)"} onMouseLeave={e=>e.currentTarget.style.background=""}>
                <div style={{ display:"flex", alignItems:"center", gap:14 }}>
                  <div style={{ width:49, height:49, borderRadius:"var(--radius-sm)", background:"rgba(255,255,255,0.05)", display:"flex", alignItems:"center", justifyContent:"center" }}><FileText size={25} color="var(--text-muted)"/></div>
                  <div><div style={{ fontWeight:500, fontSize:20 }}>{doc.filename}</div><div style={{ fontSize:18, color:"var(--text-muted)", marginTop:3 }}>{doc.file_type?.toUpperCase()||"UNKNOWN"} · {doc.upload_time||"--"}</div></div>
                </div>
                <div className="document-row-actions" style={{ display:"flex", alignItems:"center", gap:16 }}>
                  <span style={{ padding:"7px 16px", borderRadius:20, fontSize:18, fontWeight:600, background:doc.status==="done"||doc.status==="indexed"?"rgba(76,175,80,0.12)":"rgba(255,183,125,0.12)", color:doc.status==="done"||doc.status==="indexed"?"#81c784":"var(--primary)", display:"flex", alignItems:"center", gap:7 }}>
                    <span style={{ width:6, height:6, borderRadius:"50%", background:doc.status==="done"||doc.status==="indexed"?"#81c784":"var(--primary)", animation:doc.status!=="done"&&doc.status!=="indexed"?"pulse-glow 2s infinite":"none" }}/>{(doc.status==="done"||doc.status==="indexed")?"已向量化":"处理中"}
                  </span>
                  <div style={{ display:"flex", gap:4 }}>
                    <button onClick={()=>handlePreview(doc)} style={{ padding:10, borderRadius:"var(--radius-sm)", color:"var(--text-muted)", background:"none" }} title="预览"><Eye size={21}/></button>
                    <button onClick={()=>handleDownload(doc)} style={{ padding:10, borderRadius:"var(--radius-sm)", color:"var(--text-muted)", background:"none" }} title="下载"><Download size={21}/></button>
                    {isAdmin && <button onClick={()=>handleDelete(doc)} style={{ padding:10, borderRadius:"var(--radius-sm)", color:"var(--text-muted)", background:"none" }} title="删除"><Trash2 size={21}/></button>}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="glass-panel" style={{ borderRadius:"var(--radius-lg)", overflow:"hidden", marginTop:24 }}>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"16px 24px", borderBottom:"1px solid var(--border-subtle)" }}>
              <h3 style={{ fontSize:22, fontWeight:700, display:"flex", alignItems:"center", gap:9 }}><ImageIcon size={24} color="var(--primary)"/>图片库</h3>
              <button onClick={()=>document.getElementById("image-input")?.click()} style={{ display:"flex", alignItems:"center", gap:8, padding:"8px 14px", borderRadius:"var(--radius-sm)", background:"var(--primary-container)", color:"var(--primary)", fontWeight:700 }}>
                <Upload size={21}/>上传图片
              </button>
              <input id="image-input" type="file" hidden accept=".jpg,.jpeg,.png,.webp,.bmp" onChange={e=>{const f=e.target.files?.[0];if(f)handleImageUpload(f); e.currentTarget.value=""}}/>
            </div>
            <div onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();const f=e.dataTransfer.files[0];if(f)handleImageUpload(f)}} style={{ padding:24 }}>
              {imageLoading ? (
                <div style={{ padding:"32px", textAlign:"center", color:"var(--text-muted)" }}>加载中...</div>
              ) : images.length === 0 ? (
                <div style={{ padding:"44px", textAlign:"center", color:"var(--text-muted)", border:"1px dashed var(--border-glass)", borderRadius:"var(--radius)" }}>
                  <ImageIcon size={40} style={{ opacity:0.35, marginBottom:12 }}/>
                  <p>暂无图片，可点击上传或拖拽图片到此处</p>
                </div>
              ) : (
                <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(180px,1fr))", gap:16 }}>
                  {images.map(image=>(
                    <div key={image.id} style={{ border:"1px solid var(--border-glass)", borderRadius:"var(--radius)", overflow:"hidden", background:"rgba(255,255,255,0.03)" }}>
                      <img src={image.thumbnail_url} alt={image.filename} style={{ width:"100%", aspectRatio:"4 / 3", objectFit:"cover", display:"block", background:"rgba(255,255,255,0.04)" }}/>
                      <div style={{ padding:12 }}>
                        <div title={image.filename} style={{ fontSize:19, fontWeight:700, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis", marginBottom:9 }}>{image.filename}</div>
                        <div style={{ display:"flex", justifyContent:"space-between", color:"var(--text-muted)", fontSize:18, marginBottom:12 }}>
                          <span>{image.width}×{image.height}</span>
                          <span style={{ display:"flex", alignItems:"center", gap:4 }}><Flame size={13} color="var(--primary)"/>{image.download_count}</span>
                        </div>
                        <div style={{ display:"flex", gap:6 }}>
                          <a href={image.view_url} target="_blank" rel="noreferrer" style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", padding:"12px 0", borderRadius:"var(--radius-sm)", color:"var(--text-muted)", border:"1px solid var(--border-glass)" }} title="查看"><Eye size={21}/></a>
                          <button onClick={()=>handleImageDownload(image)} style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", padding:"12px 0", borderRadius:"var(--radius-sm)", color:"var(--text-muted)", border:"1px solid var(--border-glass)", background:"none" }} title="下载"><Download size={21}/></button>
                          {isAdmin && <button onClick={()=>handleImageDelete(image)} style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", padding:"12px 0", borderRadius:"var(--radius-sm)", color:"var(--text-muted)", border:"1px solid var(--border-glass)", background:"none" }} title="删除"><Trash2 size={21}/></button>}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      {toast&&<div className="toast-container"><div className={`toast${toast.error?" error":" success"}`}>{toast.msg}</div></div>}
      {preview&&(
        <div onClick={()=>setPreview(null)} style={{ position:"fixed", inset:0, zIndex:1000, background:"rgba(0,0,0,0.5)", display:"flex", alignItems:"center", justifyContent:"center" }}>
          <div onClick={e=>e.stopPropagation()} className="glass-panel" style={{ width:640, maxWidth:"90vw", maxHeight:"80vh", display:"flex", flexDirection:"column", borderRadius:"var(--radius-lg)" }}>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"16px 24px", borderBottom:"1px solid var(--border-glass)" }}>
              <h3 style={{ fontSize:22, fontWeight:700, color:"var(--primary)" }}>{preview.filename}</h3>
              <div style={{ display:"flex", gap:8, alignItems:"center" }}>
                <span style={{ fontSize:18, color:"var(--text-muted)" }}>共 {preview.total.toLocaleString()} 字</span>
                <button onClick={()=>setPreview(null)} style={{ background:"none", padding:8, color:"var(--text-muted)", cursor:"pointer", display:"flex", fontSize:23 }}>✕</button>
              </div>
            </div>
            <div style={{ flex:1, overflow:"auto", padding:"27px 31px", fontSize:21, lineHeight:1.8, color:"var(--text-primary)", whiteSpace:"pre-wrap", fontFamily:"inherit" }}>
              {preview.content}{preview.content.length >= 2000 ? "\n\n··· 内容已截断（仅显示前 2000 字）" : ""}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
