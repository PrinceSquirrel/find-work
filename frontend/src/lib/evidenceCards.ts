import type { EvidenceCard, EvidenceCardUpdate } from "../types";

export type EvidenceCardDraft = {
  title: string; category: string; organization: string; time_range: string; situation: string;
  actions: string; results: string; skills: string; user_note: string;
};

export function evidenceCardToDraft(card: EvidenceCard): EvidenceCardDraft {
  return {
    title: card.title, category: card.category, organization: card.organization, time_range: card.time_range,
    situation: card.situation, actions: card.actions.join("\n"), results: card.results.join("\n"),
    skills: card.skills.join("、"), user_note: card.user_note,
  };
}

export function splitEvidenceDraftList(value: string): string[] {
  return value.split(/[\n,，、]/).map(item => item.trim()).filter(Boolean);
}

export function evidenceDraftPayload(draft: EvidenceCardDraft): EvidenceCardUpdate {
  return {
    title: draft.title.trim(), category: draft.category, organization: draft.organization.trim(),
    time_range: draft.time_range.trim(), situation: draft.situation.trim(), user_note: draft.user_note.trim(),
    actions: splitEvidenceDraftList(draft.actions), results: splitEvidenceDraftList(draft.results), skills: splitEvidenceDraftList(draft.skills),
  };
}

export function evidenceConfirmation(card: EvidenceCard, draft: EvidenceCardDraft) {
  const dirty = JSON.stringify(evidenceDraftPayload(draft)) !== JSON.stringify(evidenceDraftPayload(evidenceCardToDraft(card)));
  const confirmed = card.status === "confirmed";
  return { dirty, disabled: confirmed && !dirty, label: confirmed ? dirty ? "重新确认" : "已确认" : "确认事实" };
}
