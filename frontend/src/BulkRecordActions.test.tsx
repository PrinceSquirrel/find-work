import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { BulkRecordActions, RecordCheckbox, removeRecordKeys, toggleRecord, visibleSelection } from "./BulkRecordActions";

describe("bulk record selection", () => {
  it("only deletes visible eligible records, excluding hidden and protected selections", () => {
    expect(visibleSelection([1, 2, 2], [2, 3, 9])).toEqual([2]);
    expect(visibleSelection([], [1])).toEqual([]);
    expect(toggleRecord([1, 2], 2)).toEqual([1]);
    expect(toggleRecord([1], 2)).toEqual([1, 2]);
  });
  it("clears only deleted caches and retains other job results", () => {
    expect(removeRecordKeys({ 1: "deleted", 2: "preserved" }, [1, 99])).toEqual({ 2: "preserved" });
  });
  it("disables destructive actions until there is an eligible selection", () => {
    const html = renderToStaticMarkup(<BulkRecordActions label="岗位" available={[1]} selected={[99]} onChange={vi.fn()} onDelete={vi.fn()} busy={false} protectedCount={1} />);
    expect(html).toMatch(/disabled=""[^>]*>批量删除/);
    expect(html).toContain("保留 1 条关联投递的岗位");
    expect(html).toContain("已选 0 / 1 条");
  });
  it("offers pending-record selection and blocks duplicate actions while busy", () => {
    const html = renderToStaticMarkup(<BulkRecordActions label="投递记录" available={[1, 2]} selected={[1]} onChange={vi.fn()} onDelete={vi.fn()} busy suggestion={{ label: "选择待核对记录", ids: [2] }} message="删除失败，可重试" />);
    expect(html).toContain("选择待核对记录");
    expect(html).toMatch(/disabled=""[^>]*>处理中…/);
    expect(html).toContain('role="status"');
  });
  it("keeps record checkboxes labeled and protects linked jobs", () => {
    const html = renderToStaticMarkup(<RecordCheckbox label="选择岗位 #7" checked={false} disabled onChange={vi.fn()} />);
    expect(html).toContain('aria-label="选择岗位 #7"');
    expect(html).toContain('disabled=""');
  });
});
