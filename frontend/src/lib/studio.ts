import type { EvidenceCard, TrustedTailorBundle } from "../types";

export function chooseConfirmedCards(cards: EvidenceCard[], selected: number[]): number[] {
  const confirmed = new Set(cards.filter(card => card.status === "confirmed").map(card => card.id));
  return [...new Set(selected)].filter(id => confirmed.has(id));
}

export function hasUnsavedClaims(bundle: TrustedTailorBundle, drafts: Record<number, string>): boolean {
  return bundle.claims.some(claim => claim.user_decision !== "rejected" && (drafts[claim.id] ?? claim.text) !== claim.text);
}

export function canExportTrusted(bundle: TrustedTailorBundle, drafts: Record<number, string>): boolean {
  const retained = bundle.claims.filter(claim => claim.user_decision !== "rejected");
  return bundle.review.trusted_evidence_finalized === true && !hasUnsavedClaims(bundle, drafts) &&
    retained.length > 0 && retained.every(claim => claim.support_status === "supported" && claim.user_decision === "accepted");
}

export function saveJobResult(current: Record<number, TrustedTailorBundle>, bundle: TrustedTailorBundle) {
  return { ...current, [bundle.job_id]: bundle };
}
