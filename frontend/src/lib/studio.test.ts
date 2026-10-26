import { describe, expect, it } from "vitest";
import type { EvidenceCard, TrustedTailorBundle } from "../types";
import { canExportTrusted, chooseConfirmedCards, hasUnsavedClaims, saveJobResult } from "./studio";

const bundle: TrustedTailorBundle = {
  id: 10, job_id: 1, review: { trusted_evidence_finalized: true },
  resume_id: 1, resume_text: "真实经历", resume_rewrite: "真实经历", project_rewrite: "",
  diff_summary: [], risk_flags: [], truth_check_passed: true, created_at: "",
  greeting: { id: 1, job_id: 1, message: "您好", tone: "", risk_flags: [], created_at: "" },
  claims: [{ id: 5, tailored_resume_id: 10, text: "真实经历", evidence_card_ids: [1], support_status: "supported", user_decision: "accepted", edit_version: 0, created_at: "", updated_at: "" }],
};

describe("single-result studio", () => {
  it("excludes missing, rejected and draft evidence", () => {
    const cards = [{ id: 1, status: "confirmed" }, { id: 2, status: "draft" }, { id: 3, status: "rejected" }] as EvidenceCard[];
    expect(chooseConfirmedCards(cards, [1, 1, 2, 3, 99])).toEqual([1]);
    expect(chooseConfirmedCards([], [1])).toEqual([]);
  });
  it("keeps results bound to their originating job even when responses arrive late", () => {
    const second = { ...bundle, id: 11, job_id: 2 };
    const state = saveJobResult(saveJobResult({}, second), bundle);
    expect(state[2]).toBe(second);
    expect(state[1]).toBe(bundle);
    expect(state[3]).toBeUndefined();
  });
  it("blocks export immediately for unsaved edits, even after finalization", () => {
    expect(canExportTrusted(bundle, {})).toBe(true);
    expect(hasUnsavedClaims(bundle, { 5: "修改后的经历" })).toBe(true);
    expect(canExportTrusted(bundle, { 5: "修改后的经历" })).toBe(false);
  });
  it("requires accepted supported claims and server finalization", () => {
    expect(canExportTrusted({ ...bundle, review: {} }, {})).toBe(false);
    expect(canExportTrusted({ ...bundle, claims: [] }, {})).toBe(false);
    expect(canExportTrusted({ ...bundle, claims: [{ ...bundle.claims[0], user_decision: "pending" }] }, {})).toBe(false);
  });
});
