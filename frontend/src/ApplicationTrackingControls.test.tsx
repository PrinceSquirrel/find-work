import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ApplicationFilterPreview, ApplicationPaginationPreview } from "./ApplicationTrackingControls";

describe("application tracking frontend preview", () => {
  it("renders three labeled, editable search fields and a disabled filter action", () => {
    const html = renderToStaticMarkup(<ApplicationFilterPreview />);
    expect(html.match(/type="search"/g)).toHaveLength(3);
    for (const label of ["岗位", "关键词", "地址"]) {
      expect(html).toMatch(new RegExp(`<label><span>${label}</span><input`));
    }
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*disabled=""/);
    expect(html).toContain('type="reset"');
    expect(html).toContain("当前仍展示全部投递记录");
  });

  it("offers the requested page sizes without presenting a fake paginated result", () => {
    const html = renderToStaticMarkup(<ApplicationPaginationPreview count={137} loading={false} />);
    expect(html).toContain('<option value="25" selected="">25 条</option>');
    expect(html).toContain('<option value="50">50 条</option>');
    expect(html).toContain('<option value="100">100 条</option>');
    expect(html).toContain("<b>137</b> 条记录");
    expect(html.match(/<button[^>]*disabled=""/g)).toHaveLength(2);
    expect(html).toContain("尚未分页");
  });

  it("shows an empty count without inventing a first page", () => {
    const html = renderToStaticMarkup(<ApplicationPaginationPreview count={0} loading={false} />);
    expect(html).toContain("<b>0</b> 条记录");
    expect(html).not.toContain("第 1 页");
  });

  it("distinguishes loading from an empty result", () => {
    const html = renderToStaticMarkup(<ApplicationPaginationPreview count={0} loading />);
    expect(html).toContain("正在读取记录");
    expect(html).not.toContain("<b>0</b>");
  });
});
