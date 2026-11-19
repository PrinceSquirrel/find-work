import { describe, expect, it } from "vitest";
import type { EvidenceCard } from "../types";
import { evidenceCardToDraft, evidenceConfirmation, evidenceDraftPayload } from "./evidenceCards";

const card = {
  id: 1, title: "接口测试", category: "project", organization: "松鼠", time_range: "2026", situation: "需求验收",
  actions: ["编写测试", "执行回归"], results: ["完成验收"], skills: ["Python", "SQL"], user_note: "真实经历", status: "confirmed",
} as EvidenceCard;

describe("evidence confirmation state", () => {
  it("disables unchanged confirmed cards", () => {
    expect(evidenceConfirmation(card, evidenceCardToDraft(card))).toEqual({ dirty: false, disabled: true, label: "已确认" });
  });
  it("requires confirmation for draft and rejected cards", () => {
    for (const status of ["draft", "rejected"] as const) {
      expect(evidenceConfirmation({ ...card, status }, evidenceCardToDraft(card)).label).toBe("确认事实");
      expect(evidenceConfirmation({ ...card, status }, evidenceCardToDraft(card)).disabled).toBe(false);
    }
  });
  it("enables reconfirmation for each changed fact and disables it after reverting", () => {
    const draft = evidenceCardToDraft(card);
    for (const field of Object.keys(draft) as (keyof typeof draft)[]) {
      expect(evidenceConfirmation(card, { ...draft, [field]: `${draft[field]}修改` })).toEqual({ dirty: true, disabled: false, label: "重新确认" });
    }
    expect(evidenceConfirmation(card, draft).disabled).toBe(true);
  });
  it("does not treat whitespace and list separators as changed facts", () => {
    const draft = { ...evidenceCardToDraft(card), title: " 接口测试 ", actions: "编写测试， 执行回归\n", skills: "Python, SQL" };
    expect(evidenceConfirmation(card, draft).disabled).toBe(true);
    expect(evidenceDraftPayload(draft).actions).toEqual(card.actions);
    expect(evidenceDraftPayload(draft)).not.toHaveProperty("status");
  });
});
