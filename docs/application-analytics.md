# 投递数据可视化统计定义

本文档定义 `GET /api/analytics/applications` 的统计口径，供前端看板、后端实现和测试用例保持一致。

## 返回结构

接口返回四组分桶：

- `totals`：全部投递记录汇总。
- `hourly`：按投递时间小时分桶，键名格式为 `HH:00`。
- `weekday`：按投递日期星期分桶，键名使用英文星期名，例如 `Monday`。
- `platform`：按岗位平台分桶，例如 `boss`、`shixiseng`。

每个分桶包含同一组指标：

- `applications`：投递记录数量。
- `read`：有明确已读证据的数量。
- `replied`：有明确回复证据的数量。
- `progressed`：进入面试或笔试/测评阶段的数量。
- `read_rate`：`read / applications`，无投递时为 `0`。
- `reply_rate`：`replied / applications`，无投递时为 `0`。
- `progress_rate`：`progressed / applications`，无投递时为 `0`。

比率保留 4 位小数。

## 状态与指标关系

`read` 只应由以下证据之一计入：

- `read_at` 不为空。
- 事件历史中存在 `read` 或后续由已读自然推进的状态。

`replied` 只应由以下证据之一计入：

- `replied_at` 不为空。
- 事件历史中存在 `replied` 或后续由回复自然推进的状态。

`progressed` 计入当前状态为：

- `interview`
- `assessment`

直接从 `applied` 进入 `rejected` 或 `closed` 不应自动计入已读或已回复。拒绝和关闭可能来自平台状态、用户手动整理或岗位下线，不能反推出招聘方已读或回复。

## 可视化建议

- 总览卡片展示 `applications`、`read_rate`、`reply_rate`、`progress_rate`。
- 小时热力图使用 `hourly`，帮助用户判断投递时间段效果。
- 星期柱状图使用 `weekday`，帮助用户比较工作日表现。
- 平台对比图使用 `platform`，帮助用户比较平台质量。
- 前端应同时展示样本量，避免在投递数量很少时过度解读百分比。

## 合规边界

统计只描述用户本地记录和明确同步结果，不应展示、推断或上传真实平台隐私数据。真实平台同步需要用户授权，失败时应保留原本地状态并提示用户人工确认。
