import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckSquare,
  ChevronDown,
  Download,
  Eye,
  FileImage,
  Filter,
  ImageUp,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
  Square,
  Tags,
  Trash2,
  X,
} from "lucide-react";

interface Asset {
  id: string;
  filename: string;
  width: number;
  height: number;
  description: string;
  tags: string;
  group_id: string;
  current_platform_usage: number;
  total_download_count: number;
  created_at: string;
  thumbnail_url: string;
  view_url: string;
  status: "queued" | "processing" | "ready" | "failed" | string;
  processing_error?: string;
  score?: number | null;
}

interface UploadBatchResponse {
  job_id: string;
  accepted: number;
  assets: Asset[];
  message: string;
}

const DEFAULT_PLATFORMS = ["小红书", "抖音", "微信公众号", "视频号", "B站", "快手", "今日头条", "微博"];
type SortMode = "recommended" | "downloads";

type SelectOption<T extends string> = {
  value: T;
  label: string;
};

function CompactSelect<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  ariaLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const selected = options.find((option) => option.value === value) ?? options[0];

  return (
    <div
      className="asset-custom-select"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <button
        type="button"
        className="asset-custom-select-trigger"
        aria-label={ariaLabel}
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span>{selected?.label ?? value}</span>
        <ChevronDown size={16} />
      </button>
      {open && (
        <div className="asset-custom-select-menu" role="listbox" aria-label={ariaLabel}>
          {options.map((option) => {
            const active = option.value === value;
            return (
              <button
                type="button"
                key={option.value}
                className={`asset-custom-select-option${active ? " selected" : ""}`}
                role="option"
                aria-selected={active}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function tokenHeaders(): Record<string, string> {
  return {};
}

async function jsonPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...tokenHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败 (${res.status})`);
  }
  return res.json();
}

function tagList(tags: string, limit = 5): string[] {
  return tags.split(/[,，;；、\s]+/).map((item) => item.trim()).filter(Boolean).slice(0, limit);
}

function statusLabel(status: string) {
  if (status === "queued") return "排队中";
  if (status === "processing") return "处理中";
  if (status === "failed") return "失败";
  return "可用";
}

function availabilityText(status: string) {
  if (status === "queued") return "等待后台视觉理解、向量化和索引写入，暂不可下载或检索。";
  if (status === "processing") return "正在生成描述词、embedding，并写入 Milvus，完成后会变为可用。";
  if (status === "failed") return "后台处理失败，当前不参与检索，也不能作为可用素材下载。";
  return "已完成视觉理解、embedding 和 Milvus 写入，可参与检索并按平台用途下载。";
}

function isPending(asset: Asset) {
  return asset.status === "queued" || asset.status === "processing";
}

export default function ImageAssets() {
  const [platforms, setPlatforms] = useState<string[]>(DEFAULT_PLATFORMS);
  const [uploadTags, setUploadTags] = useState("");
  const [platform, setPlatform] = useState(DEFAULT_PLATFORMS[0]);
  const [sortMode, setSortMode] = useState<SortMode>("recommended");
  const [query, setQuery] = useState("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [processingAssets, setProcessingAssets] = useState<Asset[]>([]);
  const [trackedIds, setTrackedIds] = useState<string[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [files, setFiles] = useState<FileList | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [toast, setToast] = useState("");
  const [previewTarget, setPreviewTarget] = useState<Asset | null>(null);
  const [downloadTarget, setDownloadTarget] = useState<Asset | null>(null);
  const [downloadPlatform, setDownloadPlatform] = useState(DEFAULT_PLATFORMS[0]);
  const [downloadNote, setDownloadNote] = useState("");

  const visibleAssets = useMemo(() => {
    const byId = new Map<string, Asset>();
    processingAssets.forEach((asset) => byId.set(asset.id, asset));
    assets.forEach((asset) => byId.set(asset.id, asset));
    return Array.from(byId.values());
  }, [assets, processingAssets]);
  const selectedCount = selectedIds.size;
  const platformOptions = useMemo<SelectOption<string>[]>(
    () => platforms.map((item) => ({ value: item, label: item })),
    [platforms],
  );
  const sortOptions = useMemo<SelectOption<SortMode>[]>(
    () => [
      { value: "recommended", label: "推荐排序" },
      { value: "downloads", label: "下载次数最多" },
    ],
    [],
  );

  const loadBasics = useCallback(async () => {
    const platformRes = await fetch("/api/image-assets/platforms", { headers: tokenHeaders(), credentials: "same-origin" });
    if (platformRes.ok) setPlatforms(await platformRes.json());
  }, []);

  const searchAssets = useCallback(async () => {
    setLoading(true);
    try {
      const data = await jsonPost<Asset[]>("/image-assets/search", {
        query,
        platform,
        sort_mode: sortMode,
        unused_first: true,
        deduplicate: true,
        limit: 48,
      });
      setAssets(data);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "搜索失败");
    } finally {
      setLoading(false);
    }
  }, [platform, query, sortMode]);

  useEffect(() => {
    loadBasics().then(searchAssets).catch(() => setToast("初始化失败"));
  }, [loadBasics, searchAssets]);

  useEffect(() => {
    if (trackedIds.length === 0) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await jsonPost<Asset[]>("/image-assets/batch-status", { ids: trackedIds });
        const active = latest.filter((asset) => asset.status !== "ready");
        const readyCount = latest.length - active.length;
        setProcessingAssets(active);
        setTrackedIds(active.map((asset) => asset.id));
        if (readyCount > 0) await searchAssets();
      } catch (error) {
        setToast(error instanceof Error ? error.message : "刷新处理状态失败");
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [trackedIds, searchAssets]);

  async function uploadBatch() {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      const form = new FormData();
      Array.from(files).forEach((file) => form.append("files", file));
      form.append("tags", uploadTags);
      const res = await fetch("/api/image-assets/upload-batch", {
        method: "POST",
        credentials: "same-origin",
        headers: tokenHeaders(),
        body: form,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "上传失败");
      }
      const result = (await res.json()) as UploadBatchResponse;
      setProcessingAssets((prev) => [...result.assets, ...prev.filter((asset) => !result.assets.some((item) => item.id === asset.id))]);
      setTrackedIds((prev) => Array.from(new Set([...prev, ...result.assets.map((asset) => asset.id)])));
      setToast(`已接收 ${result.accepted} 张图片，后台处理中`);
      setFiles(null);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  async function confirmDownload() {
    if (!downloadTarget || !downloadPlatform.trim()) return;
    try {
      const res = await fetch("/api/image-assets/download", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", ...tokenHeaders() },
        body: JSON.stringify({ id: downloadTarget.id, platform: downloadPlatform.trim(), note: downloadNote.trim() }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "下载失败");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = downloadTarget.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setDownloadTarget(null);
      setDownloadNote("");
      await searchAssets();
    } catch (error) {
      setToast(error instanceof Error ? error.message : "下载失败");
    }
  }

  async function deleteOne(asset: Asset) {
    if (!window.confirm(`确认删除「${asset.filename}」？`)) return;
    setDeleting(true);
    try {
      await jsonPost("/image-assets/delete", { id: asset.id });
      setAssets((prev) => prev.filter((item) => item.id !== asset.id));
      setProcessingAssets((prev) => prev.filter((item) => item.id !== asset.id));
      setTrackedIds((prev) => prev.filter((id) => id !== asset.id));
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(asset.id);
        return next;
      });
      setToast("图片已删除");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "删除失败");
    } finally {
      setDeleting(false);
    }
  }

  async function deleteSelected() {
    const ids = Array.from(selectedIds);
    if (ids.length === 0 || !window.confirm(`确认删除已选择的 ${ids.length} 张图片？`)) return;
    setDeleting(true);
    try {
      await jsonPost("/image-assets/delete-batch", { ids });
      setAssets((prev) => prev.filter((asset) => !selectedIds.has(asset.id)));
      setProcessingAssets((prev) => prev.filter((asset) => !selectedIds.has(asset.id)));
      setTrackedIds((prev) => prev.filter((id) => !selectedIds.has(id)));
      setSelectedIds(new Set());
      setToast(`已删除 ${ids.length} 张图片`);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "批量删除失败");
    } finally {
      setDeleting(false);
    }
  }

  function toggleSelect(assetId: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(assetId)) next.delete(assetId);
      else next.add(assetId);
      return next;
    });
  }

  function selectAllVisible() {
    const selectableIds = visibleAssets.map((asset) => asset.id);
    setSelectedIds((prev) => {
      const allSelected = selectableIds.length > 0 && selectableIds.every((id) => prev.has(id));
      return allSelected ? new Set() : new Set(selectableIds);
    });
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--body-gradient)", display: "flex", flexDirection: "column" }}>
      <header className="glass-nav page-header" style={{ height: 73, display: "flex", alignItems: "center", position: "sticky", top: 0, zIndex: 40 }}>
        <h2 style={{ fontSize: 22, fontWeight: 700, color: "var(--primary)", display: "flex", alignItems: "center", gap: 9 }}>
          <FileImage size={25} />图片资产
        </h2>
      </header>

      <main className="page-frame page-content">
        <section className="glass-panel asset-filter-panel" style={{ padding: 20, borderRadius: "var(--radius-lg)", marginBottom: 20 }}>
          <div className="asset-filter-grid">
            <label style={{ display: "grid", gap: 7, fontSize: 18, color: "var(--text-muted)" }}>
              关键词
              <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 12px", border: "1px solid var(--border-glass)", borderRadius: "var(--radius-sm)", background: "rgba(255,255,255,0.04)" }}>
                <Search size={22} />
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="多关键词用空格、逗号或顿号分隔" style={{ flex: 1, background: "none", border: 0, outline: 0, color: "var(--text-primary)" }} />
              </div>
            </label>
            <label style={{ display: "grid", gap: 7, fontSize: 18, color: "var(--text-muted)" }}>
              新媒体平台
              <CompactSelect
                ariaLabel="选择新媒体平台"
                value={platform}
                options={platformOptions}
                onChange={(nextPlatform) => {
                  setPlatform(nextPlatform);
                  setDownloadPlatform(nextPlatform);
                }}
              />
            </label>
            <label style={{ display: "grid", gap: 7, fontSize: 18, color: "var(--text-muted)" }}>
              排序
              <CompactSelect
                ariaLabel="选择排序方式"
                value={sortMode}
                options={sortOptions}
                onChange={setSortMode}
              />
            </label>
            <button onClick={searchAssets} disabled={loading} style={{ height: 49, display: "flex", alignItems: "center", gap: 9, justifyContent: "center", padding: "0 21px", borderRadius: "var(--radius-sm)", background: "var(--primary-solid)", color: "#fff", fontWeight: 700 }}>
              {loading ? <Loader2 size={23} style={{ animation: "spin 1s linear infinite" }} /> : <Filter size={23} />}筛选
            </button>
          </div>
        </section>

        <section className="glass-panel asset-upload-panel" style={{ padding: 20, borderRadius: "var(--radius-lg)", marginBottom: 20 }}>
          <div className="asset-upload-grid">
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Tags size={25} color="var(--primary)" />
              <input value={uploadTags} onChange={(e) => setUploadTags(e.target.value)} placeholder="上传标签，例如：实拍, 塞尔达, 风景" style={{ height: 49, flex: 1, minWidth: 180, borderRadius: "var(--radius-sm)", border: "1px solid var(--border-glass)", background: "rgba(255,255,255,0.04)", color: "var(--text-primary)", padding: "0 17px" }} />
            </div>
            <label style={{ height: 49, display: "flex", alignItems: "center", gap: 9, border: "1px dashed var(--border-glass)", borderRadius: "var(--radius-sm)", padding: "0 17px", color: "var(--text-muted)" }}>
              <ImageUp size={24} color="var(--primary)" />
              <span>{files?.length ? `已选择 ${files.length} 张图片` : "选择图片批量上传"}</span>
              <input type="file" multiple accept="image/*" hidden onChange={(e) => setFiles(e.target.files)} />
            </label>
            <button onClick={uploadBatch} disabled={uploading || !files?.length} style={{ height: 49, padding: "0 21px", borderRadius: "var(--radius-sm)", background: uploading || !files?.length ? "var(--text-muted)" : "var(--primary-solid)", color: "#fff", fontWeight: 700, opacity: uploading || !files?.length ? 0.55 : 1 }}>
              {uploading ? "入队中..." : "批量上传"}
            </button>
          </div>
        </section>

        <div className="asset-toolbar">
          <button onClick={selectAllVisible} className="asset-toolbar-button" title="选择当前结果">
            {visibleAssets.length > 0 && visibleAssets.every((asset) => selectedIds.has(asset.id)) ? <CheckSquare size={21} /> : <Square size={21} />}
            选择当前结果
          </button>
          <button onClick={searchAssets} className="asset-toolbar-button" title="刷新">
            <RefreshCw size={21} />刷新
          </button>
          <button onClick={deleteSelected} disabled={selectedCount === 0 || deleting} className="asset-danger-button" title="批量删除">
            <Trash2 size={21} />批量删除{selectedCount ? ` ${selectedCount}` : ""}
          </button>
        </div>

        <section className="asset-grid">
          {visibleAssets.map((asset) => {
            const selected = selectedIds.has(asset.id);
            const tags = tagList(asset.tags);
            return (
              <article key={asset.id} className={`asset-card glass-panel${selected ? " selected" : ""}`}>
                <button className="asset-select-button" onClick={() => toggleSelect(asset.id)} title={selected ? "取消选择" : "选择图片"}>
                  {selected ? <CheckSquare size={22} /> : <Square size={22} />}
                </button>
                <div className={`asset-status ${asset.status === "failed" ? "failed" : isPending(asset) ? "pending" : "ready"}`}>
                  {asset.status === "failed" && <AlertTriangle size={15} />}
                  {statusLabel(asset.status)}
                </div>
                <img src={asset.thumbnail_url} alt={asset.filename} className="asset-card-image" />
                <div className="asset-card-body">
                  <div title={asset.filename} className="asset-card-title">{asset.filename}</div>
                  <div className="asset-card-meta">
                    <span>{asset.created_at || "--"}</span>
                    <span>{platform} 使用 {asset.current_platform_usage} 次 · 总下载 {asset.total_download_count}</span>
                    <span>{asset.width}×{asset.height}{asset.score != null ? ` · 相关度 ${asset.score.toFixed(2)}` : ""}</span>
                  </div>
                  <div className="asset-tag-row">
                    {tags.length > 0 ? tags.map((tag) => <span key={tag} className="asset-tag">{tag}</span>) : <span className="asset-tag muted">暂无描述词</span>}
                  </div>
                  {asset.status === "failed" && <div className="asset-error" title={asset.processing_error}>{asset.processing_error || "后台处理失败"}</div>}
                </div>
                <div className="asset-card-actions">
                  <button onClick={() => setPreviewTarget(asset)} className="asset-icon-action" title="预览"><Eye size={21} /></button>
                  <button
                    onClick={() => { setDownloadTarget(asset); setDownloadPlatform(platform); }}
                    disabled={asset.status !== "ready"}
                    className="asset-download-action"
                    title={asset.status === "ready" ? "按平台用途下载" : "处理完成后可下载"}
                  >
                    <Download size={21} />下载
                  </button>
                  <button onClick={() => deleteOne(asset)} className="asset-icon-action danger" title="删除"><Trash2 size={21} /></button>
                </div>
              </article>
            );
          })}
        </section>

        {!loading && visibleAssets.length === 0 && (
          <div style={{ padding: 60, textAlign: "center", color: "var(--text-muted)" }}>
            <Sparkles size={42} style={{ opacity: 0.35, marginBottom: 12 }} />
            <p>暂无匹配图片，可先填写标签并批量上传。</p>
          </div>
        )}
      </main>

      {toast && <div className="toast-container"><div className="toast success" onAnimationEnd={() => window.setTimeout(() => setToast(""), 2500)}>{toast}</div></div>}

      {previewTarget && (
        <div onClick={() => setPreviewTarget(null)} className="asset-modal-backdrop">
          <div onClick={(e) => e.stopPropagation()} className="asset-preview-modal glass-panel">
            <button onClick={() => setPreviewTarget(null)} className="asset-modal-close" title="关闭"><X size={24} /></button>
            <img src={previewTarget.view_url} alt={previewTarget.filename} className="asset-preview-image" />
            <div className="asset-preview-detail">
              <h3>{previewTarget.filename}</h3>
              <p>{previewTarget.width}×{previewTarget.height} · {statusLabel(previewTarget.status)}</p>
              <p>{availabilityText(previewTarget.status)}</p>
              {previewTarget.description && <p>{previewTarget.description}</p>}
              <div className="asset-tag-row">{tagList(previewTarget.tags, 12).map((tag) => <span key={tag} className="asset-tag">{tag}</span>)}</div>
            </div>
          </div>
        </div>
      )}

      {downloadTarget && (
        <div onClick={() => setDownloadTarget(null)} className="asset-modal-backdrop">
          <div onClick={(e) => e.stopPropagation()} className="glass-panel" style={{ width: 420, maxWidth: "92vw", padding: 20, borderRadius: "var(--radius-lg)" }}>
            <h3 style={{ fontSize: 22, fontWeight: 700, marginBottom: 18 }}>填写下载用途</h3>
            <label style={{ display: "grid", gap: 7, color: "var(--text-muted)", fontSize: 18, marginBottom: 14 }}>
              新媒体平台
              <input value={downloadPlatform} onChange={(e) => setDownloadPlatform(e.target.value)} list="platform-list" style={{ height: 49, borderRadius: "var(--radius-sm)", border: "1px solid var(--border-glass)", background: "var(--surface)", color: "var(--text-primary)", padding: "0 15px" }} />
              <datalist id="platform-list">{platforms.map((item) => <option key={item} value={item} />)}</datalist>
            </label>
            <label style={{ display: "grid", gap: 7, color: "var(--text-muted)", fontSize: 18, marginBottom: 18 }}>
              备注
              <textarea value={downloadNote} onChange={(e) => setDownloadNote(e.target.value)} placeholder="可选，例如：本周推文封面" style={{ minHeight: 89, resize: "vertical", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-glass)", background: "var(--surface)", color: "var(--text-primary)", padding: 15 }} />
            </label>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button onClick={() => setDownloadTarget(null)} style={{ height: 47, padding: "0 19px", borderRadius: "var(--radius-sm)", background: "transparent", color: "var(--text-muted)" }}>取消</button>
              <button onClick={confirmDownload} style={{ height: 47, padding: "0 21px", borderRadius: "var(--radius-sm)", background: "var(--primary-solid)", color: "#fff", fontWeight: 700 }}>确认下载</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
