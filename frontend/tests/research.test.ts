import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { claimText, formatP, mergeRows, sessionTone, statusTone, STATUS_ORDER, type SessionRow } from "../lib/researchView.ts";
import type { Confirmation, RegisteredHypothesis } from "../lib/types.ts";

const NAMES = { "RandomForest": "Random Forest", "LogisticRegression": "Lojistik regresyon", "RandomForest__default": "Random Forest (varsayılan)" };

function hypothesis(id: string, overrides: Partial<RegisteredHypothesis> = {}): RegisteredHypothesis {
  return {
    id,
    subject: ["RandomForest"],
    other: ["LogisticRegression"],
    stage: "default",
    metric: "roc_auc",
    statement: "x",
    evidence: { median_difference: 0.04, wins: 5, datasets: 6, scope: "exploration" },
    digest: "d",
    registered_at: "t",
    ...overrides,
  };
}

function confirmation(id: string, overrides: Partial<Confirmation> = {}): Confirmation {
  return { id, stage: "default", status: "confirmed", p_value: 0.002, adjusted_p_value: 0.01, q_value: 0.005, median_difference: 0.03, wins: 10, losses: 0, ties: 0, datasets: 10, ...overrides };
}

describe("claimText", () => {
  it("names both sides with the plain model names", () => {
    assert.equal(claimText(["RandomForest"], ["LogisticRegression"], NAMES), "Random Forest ≻ Lojistik regresyon");
  });

  it("falls back to the key of a model without a plain name", () => {
    assert.equal(claimText(["Mystery"], ["RandomForest"], NAMES), "Mystery ≻ Random Forest");
  });

  it("writes the default control with its plain name", () => {
    assert.equal(claimText(["RandomForest"], ["RandomForest__default"], NAMES), "Random Forest ≻ Random Forest (varsayılan)");
  });

  it("joins the members of a group", () => {
    assert.equal(claimText(["RandomForest", "Mystery"], ["LogisticRegression"], NAMES), "Random Forest + Mystery ≻ Lojistik regresyon");
  });
});

describe("formatP", () => {
  it("shows a dash when there is no value", () => {
    assert.equal(formatP(null, "tr"), "–");
  });

  it("shows very small values as below one in a thousand", () => {
    assert.equal(formatP(0.0004, "tr"), "<0,001");
    assert.equal(formatP(0.0004, "en"), "<0.001");
  });

  it("writes three decimals otherwise in the language of the page", () => {
    assert.equal(formatP(0.0391, "tr"), "0,039");
    assert.equal(formatP(0.0391, "en"), "0.039");
    assert.equal(formatP(1, "en"), "1.000");
  });

  it("treats exactly one in a thousand as a normal value", () => {
    assert.equal(formatP(0.001, "en"), "0.001");
  });
});

describe("tones", () => {
  it("maps every confirmation status to a tone", () => {
    assert.equal(statusTone("confirmed"), "positive");
    assert.equal(statusTone("reversed"), "negative");
    assert.equal(statusTone("not_confirmed"), "neutral");
    assert.equal(statusTone("not_testable"), "muted");
    assert.equal(statusTone("anything else"), "muted");
  });

  it("maps every session status to a tone", () => {
    assert.equal(sessionTone("completed"), "positive");
    assert.equal(sessionTone("running"), "neutral");
    assert.equal(sessionTone("aborted"), "warning");
    assert.equal(sessionTone("failed"), "negative");
    assert.equal(sessionTone("other"), "muted");
  });

  it("orders the statuses from the most to the least interesting", () => {
    assert.deepEqual(STATUS_ORDER, ["confirmed", "reversed", "not_confirmed", "not_testable"]);
  });
});

describe("mergeRows", () => {
  it("pairs each hypothesis with its confirmation by id and keeps the registration order", () => {
    const rows = mergeRows([hypothesis("H1"), hypothesis("H2", { subject: ["LogisticRegression"], other: ["RandomForest"] })], [confirmation("H2", { status: "reversed" }), confirmation("H1")]);
    assert.deepEqual(rows.map((row: SessionRow) => [row.hypothesis.id, row.confirmation?.status]), [["H1", "confirmed"], ["H2", "reversed"]]);
  });

  it("leaves the confirmation empty before the sealed results were read", () => {
    const rows = mergeRows([hypothesis("H1")], undefined);
    assert.equal(rows.length, 1);
    assert.equal(rows[0].confirmation, null);
  });

  it("ignores a confirmation without a hypothesis", () => {
    assert.equal(mergeRows([hypothesis("H1")], [confirmation("H1"), confirmation("H9")]).length, 1);
  });

  it("gives nothing for nothing", () => {
    assert.deepEqual(mergeRows([], []), []);
  });
});
