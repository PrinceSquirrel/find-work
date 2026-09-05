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
