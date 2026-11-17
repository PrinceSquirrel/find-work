export function visibleSelection(available: number[], selected: number[]): number[] {
  const chosen = new Set(selected);
  return [...new Set(available)].filter(id => chosen.has(id));
}

export function toggleRecord(selected: number[], id: number): number[] {
  return selected.includes(id) ? selected.filter(item => item !== id) : [...selected, id];
}

export function removeRecordKeys<T>(current: Record<number, T>, removed: number[]): Record<number, T> {
  const ids = new Set(removed);
  return Object.fromEntries(Object.entries(current).filter(([id]) => !ids.has(Number(id))));
}

export function RecordCheckbox({ label, checked, disabled, onChange }: {
  label: string; checked: boolean; disabled?: boolean; onChange: () => void;
}) {
  return <input className="record-checkbox" type="checkbox" aria-label={label} checked={checked} disabled={disabled}
    onClick={event => event.stopPropagation()} onChange={onChange} />;
}

export function BulkRecordActions({ label, available, selected, onChange, onDelete, busy, protectedCount = 0, suggestion, message }: {
  label: string; available: number[]; selected: number[]; onChange: (ids: number[]) => void;
  onDelete: (ids: number[]) => void | Promise<void>; busy: boolean; protectedCount?: number;
  suggestion?: { label: string; ids: number[] }; message?: string;
}) {
  const active = visibleSelection(available, selected);
  const all = available.length > 0 && active.length === available.length;
  return <div className="bulk-record-actions" role="group" aria-label={`${label}批量操作`}>
    <label className="bulk-select-all">
      <input className="record-checkbox" type="checkbox" aria-label={`全选当前${label}`} checked={all} disabled={busy || !available.length}
        ref={node => { if (node) node.indeterminate = active.length > 0 && !all; }}
        onChange={() => onChange(all ? selected.filter(id => !available.includes(id)) : [...new Set([...selected, ...available])])} />
      全选当前结果
    </label>
    <span className="bulk-selection-count">已选 {active.length} / {available.length} 条</span>
    {protectedCount > 0 ? <small>保留 {protectedCount} 条关联投递的岗位</small> : null}
    {suggestion ? <button type="button" disabled={busy || !suggestion.ids.length} onClick={() => onChange(visibleSelection(available, suggestion.ids))}>{suggestion.label}</button> : null}
    <button type="button" disabled={busy || !selected.length} onClick={() => onChange([])}>取消选择</button>
    <button className="bulk-delete-button" type="button" disabled={busy || !active.length || active.length > 1000} onClick={() => void onDelete(active)}>{busy ? "处理中…" : "批量删除"}</button>
    {active.length > 1000 ? <small>一次最多删除 1000 条，请分批选择。</small> : null}
    {message ? <p className="bulk-action-message" role="status">{message}</p> : null}
  </div>;
}
