export type WorkspaceModule =
  | "dashboard"
  | "materials"
  | "jobs"
  | "studio"
  | "applications"
  | "agents"
  | "settings";

export type WorkspaceNavItem = {
  id: WorkspaceModule;
  label: string;
  shortLabel: string;
  description: string;
};

export type HomeFeature = {
  module: WorkspaceModule;
  title: string;
  description: string;
  keywords: string[];
};

export const WORKSPACE_NAV_ITEMS: WorkspaceNavItem[] = [
  { id: "dashboard", label: "仪表盘", shortLabel: "首页", description: "Token、费用与系统概览" },
  { id: "materials", label: "简历与资料", shortLabel: "资料", description: "简历、经历卡片与证据" },
  { id: "jobs", label: "岗位雷达", shortLabel: "岗位", description: "搜索、筛选与详情核验" },
  { id: "studio", label: "生成中心", shortLabel: "生成", description: "可信生成与人审材料" },
  { id: "applications", label: "投递跟踪", shortLabel: "投递", description: "投递漏斗与结果同步" },
  { id: "agents", label: "Agent 运行", shortLabel: "Agent", description: "运行状态与最近动作" },
  { id: "settings", label: "系统设置", shortLabel: "设置", description: "模型、连接与系统检查" },
];

export const HOME_FEATURES: HomeFeature[] = [
  {
    module: "materials",
    title: "可信资料库",
    description: "沉淀简历、经历卡片与可追溯证据",
    keywords: ["简历", "经历", "资料", "证据"],
  },
  {
    module: "jobs",
    title: "岗位雷达",
    description: "搜索真实岗位并检查 JD 完整度",
    keywords: ["岗位", "搜索", "JD", "BOSS", "实习僧"],
  },
  {
    module: "studio",
    title: "可信生成",
    description: "基于已确认事实生成定制求职材料",
    keywords: ["生成", "模型", "材料", "简历", "招呼语"],
  },
  {
    module: "applications",
    title: "投递闭环",
    description: "预检、确认、平台证明与进度追踪",
    keywords: ["投递", "进度", "跟踪", "回复", "已读"],
  },
];

export function filterHomeFeatures(query: string): HomeFeature[] {
  const normalizedQuery = query.trim().toLocaleLowerCase("zh-CN");
  if (!normalizedQuery) return HOME_FEATURES;
  return HOME_FEATURES.filter((feature) =>
    [feature.title, feature.description, ...feature.keywords]
      .join(" ")
      .toLocaleLowerCase("zh-CN")
      .includes(normalizedQuery),
  );
}

export function getWorkspaceModule(moduleId: WorkspaceModule): WorkspaceNavItem {
  return WORKSPACE_NAV_ITEMS.find((item) => item.id === moduleId) ?? WORKSPACE_NAV_ITEMS[0];
}
