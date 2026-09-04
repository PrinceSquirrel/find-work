import { describe, expect, it } from "vitest";

import {
  filterHomeFeatures,
  getWorkspaceModule,
  HOME_FEATURES,
  WORKSPACE_NAV_ITEMS,
  WORKSPACE_PANEL_TITLES,
} from "./workspace";

describe("workspace navigation", () => {
  it("keeps the seven agreed product modules in a stable order", () => {
    expect(WORKSPACE_NAV_ITEMS.map((item) => item.id)).toEqual([
      "dashboard",
      "materials",
      "jobs",
      "studio",
      "applications",
      "agents",
      "settings",
    ]);
  });

  it("keeps dashboard-only activity blocks out of home feature shortcuts", () => {
    expect(HOME_FEATURES.map((feature) => feature.module)).toEqual([
      "materials",
      "jobs",
      "studio",
      "applications",
    ]);
    expect(HOME_FEATURES.map((feature) => feature.title)).not.toContain("最近动作");
    expect(HOME_FEATURES.map((feature) => feature.title)).not.toContain("求职进度漏斗");
  });

  it("filters shortcuts with Chinese product terms", () => {
    expect(filterHomeFeatures("岗位").map((feature) => feature.module)).toEqual(["jobs"]);
    expect(filterHomeFeatures("简历").map((feature) => feature.module)).toEqual([
      "materials",
      "studio",
    ]);
    expect(filterHomeFeatures("  ")).toHaveLength(4);
  });

  it("returns the current module label and description", () => {
    expect(getWorkspaceModule("agents")).toMatchObject({
      label: "Agent 运行",
      description: "运行状态与最近动作",
    });
  });

  it("places the funnel and activity history outside the dashboard", () => {
    expect(WORKSPACE_PANEL_TITLES.dashboard).not.toContain("求职进度漏斗");
    expect(WORKSPACE_PANEL_TITLES.dashboard).not.toContain("最近动作");
    expect(WORKSPACE_PANEL_TITLES.applications).toContain("求职进度漏斗");
    expect(WORKSPACE_PANEL_TITLES.agents).toContain("最近动作");
  });
});
