import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ApplicationFiltersBar, ApplicationPagination, applyApplicationFilters, INITIAL_APPLICATION_QUERY } from "./ApplicationTrackingControls";
import type { ApplicationPage } from "./lib/api";

describe("live tracking controls", () => {
  const empty = { items: [], total: 0, page: 1, page_size: 25, pages: 0, statistics_scope: "all_applications" } as ApplicationPage;
  const noop = () => {};
  const pagination = (data: ApplicationPage | null, loading = false, error = "") => renderToStaticMarkup(<ApplicationPagination data={data} pageSize={25} loading={loading} error={error} onPage={noop} onPageSize={noop} onRetry={noop} />);
  it("applies trimmed AND filters and resets page while retaining size", () => {
    expect(applyApplicationFilters({ ...INITIAL_APPLICATION_QUERY, page: 4, page_size: 50 }, { position: " Python ", keyword: "SQL", location: " 张江 " })).toEqual({ position: "Python", keyword: "SQL", location: "张江", page: 1, page_size: 50 });
  });
  it("has real labeled filter controls and states the statistics and selection scope", () => {
    const html = renderToStaticMarkup(<ApplicationFiltersBar value={INITIAL_APPLICATION_QUERY} onChange={noop} onApply={noop} onReset={noop} />);
    expect(html.match(/type="search"/g)).toHaveLength(3);
    expect(html).not.toContain("disabled");
    expect(html).toContain("统计仍为全部投递");
    expect(html).toContain("清空勾选");
    expect(html.match(/maxLength="200"/g)).toHaveLength(3);
  });
  it("renders genuine ranges and first/last page boundaries", () => {
    const first = pagination({ ...empty, total: 137, pages: 6 });
    expect(first).toContain("第 1–25 条");
    expect(first).toContain("第 1 / 6 页");
    expect(first.match(/<button[^>]*disabled=""/g)).toHaveLength(1);
    expect(pagination({ ...empty, total: 137, pages: 6, page: 6 })).toContain("第 126–137 条");
  });
  it("distinguishes empty, loading and retryable failure without fake pages", () => {
    expect(pagination(empty)).not.toContain("第 1 /");
    expect(pagination(null, true)).toContain("正在读取记录");
    const failed = pagination(null, false, "网络错误");
    expect(failed).toContain("重试查询");
    expect(failed).not.toContain("共 0 条");
  });
});

describe("application tracking active UI guardrails", () => {
  const noop = () => {};
  const page: ApplicationPage = { items: [], total: 137, page: 1, page_size: 25, pages: 6, statistics_scope: "all_applications" };
  it("renders labeled fields and freezes filters during record mutations", () => {
    const html = renderToStaticMarkup(<ApplicationFiltersBar value={INITIAL_APPLICATION_QUERY} onChange={noop} onApply={noop} onReset={noop} disabled />);
    expect(html.match(/type="search"/g)).toHaveLength(3);
    for (const label of ["岗位", "关键词", "地址"]) {
      expect(html).toMatch(new RegExp(`<label><span>${label}</span><input`));
    }
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*disabled=""/);
    expect(html).toContain('type="reset"');
    expect(html.match(/disabled=""/g)).toHaveLength(5);
  });

  it("offers the requested page sizes with the actual total and active next page", () => {
    const html = renderToStaticMarkup(<ApplicationPagination data={page} pageSize={25} loading={false} error="" onPage={noop} onPageSize={noop} onRetry={noop} />);
    expect(html).toContain('<option value="25" selected="">25 条</option>');
    expect(html).toContain('<option value="50">50 条</option>');
    expect(html).toContain('<option value="100">100 条</option>');
    expect(html).toContain("<b>137</b> 条");
    expect(html.match(/<button[^>]*disabled=""/g)).toHaveLength(1);
    expect(html).not.toContain("尚未分页");
  });

  it("freezes both page actions and size while a mutation is in flight", () => {
    const html = renderToStaticMarkup(<ApplicationPagination data={page} pageSize={25} loading={false} error="" onPage={noop} onPageSize={noop} onRetry={noop} disabled />);
    expect(html.match(/disabled=""/g)).toHaveLength(3);
  });

  it("distinguishes loading from an empty result", () => {
    const html = renderToStaticMarkup(<ApplicationPagination data={null} pageSize={25} loading error="" onPage={noop} onPageSize={noop} onRetry={noop} />);
    expect(html).toContain("正在读取记录");
    expect(html).not.toContain("<b>0</b>");
  });
});
