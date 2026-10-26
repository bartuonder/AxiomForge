import type { CampaignPlanSpec } from "./types";

const MAX_REFERENCES = 3;
const ARXIV_ID =
  /(?:arxiv\.org\/(?:abs|pdf|html)\/|arxiv:\s*)(\d{4}\.\d{4,5}(?!\d)|[a-z][a-z-]*(?:\.[a-z]{2})?\/\d{7}(?!\d))(?:v\d+)?/gi;

export function arxivReferences(query: string): string[] {
  const found = Array.from(query.matchAll(ARXIV_ID), (match) => match[1]);
  return Array.from(new Set(found)).slice(0, MAX_REFERENCES);
}

export function tuningLabel(tuning: CampaignPlanSpec["tuning"]): string | null {
  if (!tuning || !tuning.iterations) {
    return null;
  }
  return `Tuned: random search of ${tuning.iterations} configurations per model, ${tuning.folds ?? 3}-fold cross-validation`;
}

export function sourceLabel(source: CampaignPlanSpec["source"]): string | null {
  if (!source?.title) {
    return null;
  }
  return source.citation ? `${source.title} (${source.citation})` : source.title;
}
