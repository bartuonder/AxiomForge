import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { arxivReferences, sourceLabel, tuningLabel } from "../lib/campaignView.ts";

describe("arxivReferences", () => {
  it("finds abs, pdf and html links", () => {
    assert.deepEqual(arxivReferences("see https://arxiv.org/abs/2207.08815v2"), ["2207.08815"]);
    assert.deepEqual(arxivReferences("http://arxiv.org/pdf/2207.08815v3.pdf"), ["2207.08815"]);
    assert.deepEqual(arxivReferences("https://arxiv.org/html/2106.03253"), ["2106.03253"]);
  });

  it("finds arXiv markers in any case and with a space", () => {
    assert.deepEqual(arxivReferences("check arXiv:2106.03253 please"), ["2106.03253"]);
    assert.deepEqual(arxivReferences("ARXIV: 2106.03253v1"), ["2106.03253"]);
  });

  it("finds old style identifiers", () => {
    assert.deepEqual(arxivReferences("arxiv.org/abs/cs/0112017v1"), ["cs/0112017"]);
    assert.deepEqual(arxivReferences("arXiv:hep-th/9901001"), ["hep-th/9901001"]);
  });

  it("keeps the order, drops duplicates and caps at three", () => {
    assert.deepEqual(arxivReferences("arXiv:1706.03762 and arxiv.org/abs/2207.08815 and arXiv:1706.03762v2"), ["1706.03762", "2207.08815"]);
    assert.equal(arxivReferences("arXiv:2207.00001 arXiv:2207.00002 arXiv:2207.00003 arXiv:2207.00004").length, 3);
  });

  it("ignores bare numbers and numbers that are too long", () => {
    assert.deepEqual(arxivReferences("version 2207.08815 without a marker"), []);
    assert.deepEqual(arxivReferences("arXiv:2207.123456"), []);
    assert.deepEqual(arxivReferences("arxiv.org/abs/cs/01120171"), []);
    assert.deepEqual(arxivReferences(""), []);
  });
});

describe("tuningLabel", () => {
  it("describes the search", () => {
    assert.equal(tuningLabel({ iterations: 12, folds: 3 }), "Tuned: random search of 12 configurations per model, 3-fold cross-validation");
  });

  it("is empty without tuning", () => {
    assert.equal(tuningLabel(undefined), null);
    assert.equal(tuningLabel({}), null);
  });
});

describe("sourceLabel", () => {
  it("joins the title and the citation", () => {
    assert.equal(sourceLabel({ title: "Why do trees win", citation: "Grinsztajn et al., arXiv:2207.08815 (2022)" }), "Why do trees win (Grinsztajn et al., arXiv:2207.08815 (2022))");
  });

  it("uses the title alone", () => {
    assert.equal(sourceLabel({ title: "Why do trees win" }), "Why do trees win");
  });

  it("is empty without a title", () => {
    assert.equal(sourceLabel({ citation: "x" }), null);
    assert.equal(sourceLabel(undefined), null);
  });
});
