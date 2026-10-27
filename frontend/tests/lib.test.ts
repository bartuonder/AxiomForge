import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { displayTitle, hiddenTestCount, isUserCampaign, visibleCampaigns } from "../lib/campaignList.ts";
import { barPercent, chartRange, etaMinutes, formatNumber, formatSigned, minutes, ratio, tonePalette, TONES, winner } from "../lib/format.ts";
import { otherTheme, parseTheme, resolveTheme, THEME_SCRIPT, THEME_STORAGE_KEY } from "../lib/theme.ts";
import { DEFAULT_LANGUAGE, LANGUAGES, MESSAGES, parseLanguage, translate } from "../lib/i18n.ts";

describe("i18n", () => {
  it("has the same keys in every language and no empty text", () => {
    const turkish = Object.keys(MESSAGES.tr).sort();
    assert.deepEqual(Object.keys(MESSAGES.en).sort(), turkish);
    for (const language of LANGUAGES) {
      for (const [key, text] of Object.entries(MESSAGES[language])) {
        assert.ok(text.trim().length > 0, `${language}:${key} is empty`);
      }
    }
  });

  it("uses the same placeholders in both languages", () => {
    const placeholders = (text: string) => (text.match(/\{\w+\}/g) ?? []).sort().join(",");
    for (const key of Object.keys(MESSAGES.tr) as (keyof typeof MESSAGES.tr)[]) {
      assert.equal(placeholders(MESSAGES.en[key]), placeholders(MESSAGES.tr[key]), key);
    }
  });

  it("fills placeholders and keeps unknown ones", () => {
    assert.equal(translate("tr", "list.progress", { finished: 3, total: 9 }), "3 / 9 veri seti tamamlandı");
    assert.equal(translate("en", "list.progress", { finished: 3, total: 9 }), "3 / 9 datasets finished");
    assert.equal(translate("tr", "list.progress", { finished: 3 }), "3 / {total} veri seti tamamlandı");
  });

  it("parses a stored language and falls back to Turkish", () => {
    assert.equal(parseLanguage("en"), "en");
    assert.equal(parseLanguage("tr"), "tr");
    assert.equal(parseLanguage("de"), DEFAULT_LANGUAGE);
    assert.equal(parseLanguage(null), "tr");
    assert.equal(parseLanguage(undefined), "tr");
    assert.equal(DEFAULT_LANGUAGE, "tr");
  });

  it("names every step the timeline can show", () => {
    for (const step of ["literature_node", "planner_node", "experiment_node", "verifier_node", "report_node", "consistency_checker_node", "campaign_planner_node", "campaign_node", "meta_report_node", "meta_consistency_node"]) {
      assert.ok(`step.${step}` in MESSAGES.tr, step);
    }
  });
});

describe("format", () => {
  it("formats numbers by language", () => {
    assert.equal(formatNumber(0.0425, "tr", 3), "0,043");
    assert.equal(formatNumber(0.0425, "en", 3), "0.043");
    assert.equal(formatNumber(1.5, "en", 0), "2");
  });

  it("signs differences", () => {
    assert.equal(formatSigned(0.0425, "tr", 3), "+0,043");
    assert.equal(formatSigned(-0.0425, "en", 3), "−0.043");
    assert.equal(formatSigned(0, "en", 3), "0.000");
  });

  it("writes a ratio", () => {
    assert.equal(ratio(9, 9), "9 / 9");
    assert.equal(ratio(0, 5), "0 / 5");
  });

  it("starts the chart axis below the lowest score", () => {
    const points = [{ dataset: "a", label: "A", subject: 0.92, other: 0.85 }, { dataset: "b", label: "B", subject: 0.8, other: 0.77 }];
    assert.deepEqual(chartRange(points), { start: 0.7, end: 1 });
    assert.deepEqual(chartRange([{ dataset: "a", label: "A", subject: 0.52, other: 0.6 }]), { start: 0.4, end: 1 });
    assert.deepEqual(chartRange([{ dataset: "a", label: "A", subject: 0.02, other: 0.1 }]), { start: 0, end: 1 });
    assert.deepEqual(chartRange([]), { start: 0, end: 1 });
  });

  it("turns a score into a bar width", () => {
    const range = { start: 0.5, end: 1 };
    assert.equal(barPercent(0.5, range), 0);
    assert.equal(barPercent(0.75, range), 50);
    assert.equal(barPercent(1, range), 100);
    assert.equal(barPercent(0.2, range), 0);
    assert.equal(barPercent(1.4, range), 100);
    assert.equal(barPercent(0.7, { start: 1, end: 1 }), 0);
    assert.equal(barPercent(1.2, { start: 1, end: 1 }), 0);
  });

  it("finds the winner of a point", () => {
    assert.equal(winner({ dataset: "a", label: "A", subject: 0.9, other: 0.8 }), "subject");
    assert.equal(winner({ dataset: "a", label: "A", subject: 0.7, other: 0.8 }), "other");
    assert.equal(winner({ dataset: "a", label: "A", subject: 0.8, other: 0.8 }), "tie");
  });

  it("tells the minutes left, none under one minute", () => {
    assert.equal(etaMinutes(0), 0);
    assert.equal(etaMinutes(59), 0);
    assert.equal(etaMinutes(60), 1);
    assert.equal(etaMinutes(89), 1);
    assert.equal(etaMinutes(90), 2);
    assert.equal(etaMinutes(420), 7);
  });

  it("rounds minutes up to at least one", () => {
    assert.equal(minutes(10), 1);
    assert.equal(minutes(90), 2);
    assert.equal(minutes(600), 10);
  });

  it("gives every tone a palette and falls back for unknown tones", () => {
    for (const tone of ["positive", "negative", "neutral", "warning", "muted"]) {
      assert.ok(tonePalette(tone).badge.length > 0);
    }
    assert.equal(tonePalette("weird"), TONES.muted);
    assert.notEqual(tonePalette("positive").badge, tonePalette("negative").badge);
  });
});

describe("campaign list", () => {
  const items = [
    { id: "1", title: "Trees against networks", statement: "Trees beat nets", origin: "console", status: "completed", updated: "2026-10-27" },
    { id: "2", title: "Benchmark run", statement: "Forests beat trees", origin: "cli", status: "completed", updated: "2026-10-26" },
    { id: "3", title: "Old run", statement: "", origin: undefined, status: "completed", updated: "2026-10-25" },
    { id: "4", title: "From the API", statement: "Boosting beats regression", origin: "api", status: "running", updated: "2026-10-27" },
  ];

  it("tells user runs from tests", () => {
    assert.equal(isUserCampaign("console"), true);
    assert.equal(isUserCampaign("api"), true);
    assert.equal(isUserCampaign("cli"), false);
    assert.equal(isUserCampaign("unknown"), false);
    assert.equal(isUserCampaign(undefined), false);
  });

  it("hides tests by default", () => {
    assert.deepEqual(visibleCampaigns(items, false, "").map((item) => item.id), ["1", "4"]);
    assert.deepEqual(visibleCampaigns(items, true, "").map((item) => item.id), ["1", "2", "3", "4"]);
  });

  it("searches the title and the claim sentence without regard to case", () => {
    assert.deepEqual(visibleCampaigns(items, true, "FORESTS").map((item) => item.id), ["2"]);
    assert.deepEqual(visibleCampaigns(items, true, " nets ").map((item) => item.id), ["1"]);
    assert.deepEqual(visibleCampaigns(items, false, "forests"), []);
    assert.deepEqual(visibleCampaigns(items, true, "nothing like this"), []);
  });

  it("counts the hidden runs", () => {
    assert.equal(hiddenTestCount(items), 2);
    assert.equal(hiddenTestCount([]), 0);
  });

  it("names a run by its title, then its claim, then the fallback", () => {
    assert.equal(displayTitle(items[0], "x"), "Trees against networks");
    assert.equal(displayTitle({ ...items[0], title: "  " }, "x"), "Trees beat nets");
    assert.equal(displayTitle({ ...items[0], title: "", statement: " " }, "Unnamed"), "Unnamed");
    assert.equal(displayTitle({ ...items[0], title: "", statement: undefined }, "Unnamed"), "Unnamed");
  });
});

describe("theme", () => {
  it("accepts only the two known themes", () => {
    assert.equal(parseTheme("dark"), "dark");
    assert.equal(parseTheme("light"), "light");
    for (const value of ["", "auto", "DARK", null, undefined]) {
      assert.equal(parseTheme(value), null);
    }
  });

  it("follows the system until the user chooses", () => {
    assert.equal(resolveTheme(null, true), "dark");
    assert.equal(resolveTheme(null, false), "light");
    assert.equal(resolveTheme("light", true), "light");
    assert.equal(resolveTheme("dark", false), "dark");
  });

  it("switches to the other theme", () => {
    assert.equal(otherTheme("dark"), "light");
    assert.equal(otherTheme("light"), "dark");
  });

  it("runs before the page paints and uses the same storage key", () => {
    assert.ok(THEME_SCRIPT.includes(`"${THEME_STORAGE_KEY}"`));
    const document = { documentElement: { dataset: {} as Record<string, string> } };
    const storage = { getItem: () => "dark" };
    new Function("document", "localStorage", THEME_SCRIPT)(document, storage);
    assert.equal(document.documentElement.dataset.theme, "dark");
  });

  it("ignores a stored value that is not a theme and a storage that throws", () => {
    const document = { documentElement: { dataset: {} as Record<string, string> } };
    new Function("document", "localStorage", THEME_SCRIPT)(document, { getItem: () => "blue" });
    assert.equal(document.documentElement.dataset.theme, undefined);
    new Function("document", "localStorage", THEME_SCRIPT)(document, {
      getItem: () => {
        throw new Error("blocked");
      },
    });
    assert.equal(document.documentElement.dataset.theme, undefined);
  });
});
