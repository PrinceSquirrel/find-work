import { useEffect, useState } from "react";
import { api, type ApplicationFilters, type ApplicationPage, type ApplicationQuery } from "./lib/api";

export const EMPTY_APPLICATION_FILTERS: ApplicationFilters = { position: "", keyword: "", location: "" };
export const INITIAL_APPLICATION_QUERY: ApplicationQuery = { ...EMPTY_APPLICATION_FILTERS, page: 1, page_size: 25 };

export function applyApplicationFilters(query: ApplicationQuery, filters: ApplicationFilters): ApplicationQuery {
  return { ...query, ...Object.fromEntries(Object.entries(filters).map(([key, value]) => [key, value.trim()])), page: 1 };
}

export function useApplicationQuery(active: boolean, revision: number) {
  const [query, setQuery] = useState<ApplicationQuery>(INITIAL_APPLICATION_QUERY);
  const [draft, setDraft] = useState<ApplicationFilters>(EMPTY_APPLICATION_FILTERS);
  const [retryVersion, setRetryVersion] = useState(0);
  const key = JSON.stringify([query, revision, retryVersion]);
  const [result, setResult] = useState<{ key: string; data: ApplicationPage | null; error: string; loading: boolean }>({ key: "", data: null, error: "", loading: false });
  useEffect(() => {
    if (!active) return;
    let current = true;
    const controller = new AbortController();
    setResult({ key, data: null, error: "", loading: true });
    void api.getApplicationPage(query, controller.signal).then(data => {
      if (current) setResult({ key, data, error: "", loading: false });
    }).catch(error => {
      if (current) setResult({ key, data: null, error: error instanceof Error ? error.message : "查询失败，请重试", loading: false });
    });
    return () => { current = false; controller.abort(); };
  }, [active, key]);
  const loading = active && (result.loading || result.key !== key);
  const data = !loading && result.key === key ? result.data : null;
  return { query, setQuery, draft, setDraft, data, loading, error: result.key === key ? result.error : "", retry: () => setRetryVersion(value => value + 1) };
}

export function ApplicationFiltersBar({ value, onChange, onApply, onReset, disabled = false }: {
  value: ApplicationFilters; onChange: (value: ApplicationFilters) => void;
  onApply: () => void; onReset: () => void; disabled?: boolean;
}) {
  return <form className="application-filters" aria-label="投递筛选" onSubmit={event => { event.preventDefault(); onApply(); }} onReset={event => { event.preventDefault(); onReset(); }}>
    <div className="tracking-section-heading"><div><span className="eyebrow">FIND YOUR NEXT CHAPTER</span><h3>找到想跟进的机会</h3></div><span className="tracking-preview-badge">组合筛选</span></div>
    <div className="application-filter-fields">
      {([ ["position", "岗位", "例如：产品经理、数据分析"], ["keyword", "关键词", "公司、岗位描述或最新备注"], ["location", "地址", "仅匹配有来源的岗位地点"] ] as const).map(([name, label, placeholder]) =>
        <label key={name}><span>{label}</span><input name={name} type="search" maxLength={200} value={value[name]} onChange={event => onChange({ ...value, [name]: event.target.value })} placeholder={placeholder} autoComplete="off" disabled={disabled} /></label>)}
    </div>
    <div className="application-filter-actions"><p>条件同时满足；仅筛选下方列表，统计仍为全部投递。换页或筛选将清空勾选。</p><div><button type="reset" disabled={disabled}>重置条件</button><button type="submit" className="primary" disabled={disabled}>筛选记录</button></div></div>
  </form>;
}

export function ApplicationPagination({ data, pageSize, loading, error, onPage, onPageSize, onRetry, disabled = false }: {
  data: ApplicationPage | null; pageSize: 25 | 50 | 100; loading: boolean; error: string;
  onPage: (page: number) => void; onPageSize: (size: 25 | 50 | 100) => void; onRetry: () => void; disabled?: boolean;
}) {
  const blocked = loading || disabled;
  return <div className="application-pagination" aria-label="投递分页">
    <p aria-live="polite">{loading ? "正在读取记录…" : error ? "查询失败，请重试" : data?.total ? <>第 {(data.page - 1) * data.page_size + 1}–{Math.min(data.page * data.page_size, data.total)} 条 · 共 <b>{data.total}</b> 条</> : "共 0 条记录"}</p>
    <label><span>每页显示</span><select name="applicationPageSize" value={pageSize} disabled={blocked} onChange={event => onPageSize(Number(event.target.value) as 25 | 50 | 100)}>{[25, 50, 100].map(size => <option value={size} key={size}>{size} 条</option>)}</select></label>
    <nav aria-label="投递结果翻页"><button type="button" disabled={blocked || !data?.pages || data.page <= 1} onClick={() => onPage((data?.page ?? 1) - 1)}>‹ 上一页</button><span>{data?.pages ? `第 ${data.page} / ${data.pages} 页` : "暂无页码"}</span><button type="button" disabled={blocked || !data?.pages || data.page >= data.pages} onClick={() => onPage((data?.page ?? 1) + 1)}>下一页 ›</button></nav>
    {error ? <button type="button" disabled={blocked} onClick={onRetry}>重试查询</button> : null}
  </div>;
}

// Kept only until the new bounded query is connected in App in the next small stage.
export function ApplicationFilterPreview() {
  return (
    <form className="application-filters" aria-label="投递筛选预览" onSubmit={(event) => event.preventDefault()}>
      <div className="tracking-section-heading">
        <div>
          <span className="eyebrow">FIND YOUR NEXT CHAPTER</span>
          <h3>找到想跟进的机会</h3>
        </div>
        <span className="tracking-preview-badge">界面预览</span>
      </div>
      <div className="application-filter-fields">
        <label>
          <span>岗位</span>
          <input name="position" type="search" placeholder="例如：产品经理、数据分析" autoComplete="off" />
        </label>
        <label>
          <span>关键词</span>
          <input name="keyword" type="search" placeholder="搜索公司、岗位描述或备注" autoComplete="off" />
        </label>
        <label>
          <span>地址</span>
          <input name="location" type="search" placeholder="例如：上海、浦东、张江" autoComplete="off" />
        </label>
      </div>
      <div className="application-filter-actions">
        <p id="application-filter-preview-note">筛选与分页待接入，当前仍展示全部投递记录。</p>
        <div>
          <button type="reset">重置条件</button>
          <button type="submit" className="primary" disabled aria-describedby="application-filter-preview-note">筛选记录</button>
        </div>
      </div>
    </form>
  );
}

export function ApplicationPaginationPreview({ count, loading }: { count: number; loading: boolean }) {
  return (
    <div className="application-pagination" aria-label="投递分页预览">
      <p aria-live="polite">{loading ? "正在读取记录…" : <>共 <b>{count}</b> 条记录</>}<span> · 尚未分页</span></p>
      <label>
        <span>每页显示</span>
        <select name="applicationPageSize" defaultValue="25" aria-describedby="application-pagination-note">
          <option value="25">25 条</option>
          <option value="50">50 条</option>
          <option value="100">100 条</option>
        </select>
      </label>
      <nav aria-label="投递结果翻页">
        <button type="button" disabled aria-describedby="application-pagination-note">‹ 上一页</button>
        <span id="application-pagination-note">分页待接入</span>
        <button type="button" disabled aria-describedby="application-pagination-note">下一页 ›</button>
      </nav>
    </div>
  );
}
