import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { reportFilename, slug } from "../lib/download.ts";

describe("slug", () => {
  it("lowercases and joins words with dashes", () => {
    assert.equal(slug("Trees against Networks"), "trees-against-networks");
  });

  it("turns Turkish letters into plain ones", () => {
    assert.equal(slug("Ağaç Tabanlı Modeller Sinir Ağından İyi mi?"), "agac-tabanli-modeller-sinir-agindan-iyi-mi");
    assert.equal(slug("ÇĞİÖŞÜ çğıöşü"), "cgiosu-cgiosu");
  });

  it("drops accents and symbols", () => {
    assert.equal(slug("Café: (ROC-AUC) 0.85!"), "cafe-roc-auc-0-85");
  });

  it("trims dashes at both ends", () => {
    assert.equal(slug("  --Hello--  "), "hello");
  });

  it("is empty for text without letters or digits", () => {
    assert.equal(slug("???"), "");
    assert.equal(slug(""), "");
  });

  it("is cut at sixty characters without a dangling dash", () => {
    const long = slug("word ".repeat(30));
    assert.ok(long.length <= 60);
    assert.ok(!long.endsWith("-"));
    assert.equal(slug("a".repeat(59) + " b"), "a".repeat(59));
    assert.equal(slug("a".repeat(70)).length, 60);
  });
});

describe("reportFilename", () => {
  it("joins the title and the start of the id", () => {
    assert.equal(reportFilename("Trees against networks", "0123456789abcdef"), "trees-against-networks-01234567.md");
  });

  it("falls back to a plain name", () => {
    assert.equal(reportFilename("???", "abc"), "report-abc.md");
  });

  it("keeps a short id whole", () => {
    assert.equal(reportFilename("T", "g-1"), "t-g-1.md");
  });
});
