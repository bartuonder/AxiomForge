import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { LanguageProvider } from "../components/LanguageProvider.tsx";
import { ResearchTable } from "../components/ResearchTable.tsx";
import { SessionCards } from "../components/SessionList.tsx";
import { SessionDetails } from "../components/SessionView.tsx";
import type { Confirmation, RegisteredHypothesis, SessionDetail, SessionSummary } from "../lib/types.ts";

const VOCAB = {
  models: { RandomForest: "Random Forest", LogisticRegression: "Lojistik regresyon" },
  datasets: { tb_credit: "Kredi riski", tb_pol: "Telekomünikasyon verisi" },
  metrics: {},
};

function render(node: React.ReactNode, language: "tr" | "en" = "tr"): string {
  return renderToStaticMarkup(
    <LanguageProvider serverLanguage={language} initialNames={VOCAB}>
      {node}
    </LanguageProvider>,
  );
}

const HYPOTHESIS: RegisteredHypothesis = {
  id: "H1",
  subject: ["RandomForest"],
  other: ["LogisticRegression"],
  stage: "default",
  metric: "roc_auc",
  statement: "x",
  evidence: { median_difference: 0.04, wins: 5, datasets: 6, scope: "exploration" },
  digest: "d",
  registered_at: "t",
};

const CONFIRMATION: Confirmation = {
  id: "H1",
  stage: "default",
  status: "confirmed",
  p_value: 0.0004,
  adjusted_p_value: 0.012,
  q_value: 0.01,
  median_difference: 0.031,
  wins: 10,
  losses: 0,
  ties: 0,
  datasets: 10,
};

const SUMMARY: SessionSummary = {
  id: "real-1",
  status: "completed",
  reason: "",
  created: "t",
  finished: "t",
  models: ["RandomForest", "LogisticRegression"],
  explore: ["tb_credit"],
  confirm: ["tb_pol"],
  budget: 25,
  registered: 2,
  counts: { confirmed: 1, reversed: 0, not_confirmed: 1, not_testable: 0 },
  stages: [{ name: "default", finished: 16, failed: 0 }],
};

function detail(overrides: Partial<SessionDetail> = {}): SessionDetail {
  return { summary: SUMMARY, intact: true, session: { hypotheses: [HYPOTHESIS], confirmations: [CONFIRMATION], skipped: [] }, ...overrides };
}

describe("ResearchTable", () => {
  const rows = [{ hypothesis: HYPOTHESIS, confirmation: CONFIRMATION }];

  it("writes the claim with plain model names and the two effects apart", () => {
    const html = render(<ResearchTable rows={rows} />);
    assert.match(html, /Random Forest ≻ Lojistik regresyon/);
    assert.match(html, /\+0,040 · 5\/6/);
    assert.match(html, /\+0,031 · 10\/10/);
  });

  it("shows the p values in the language of the page and the status badge", () => {
    const html = render(<ResearchTable rows={rows} />);
    assert.match(html, /&lt;0,001/);
    assert.match(html, /0,012/);
    assert.match(html, /Doğrulandı/);
  });

  it("has a caption, column headers and row headers for screen readers", () => {
    const html = render(<ResearchTable rows={rows} />);
    assert.match(html, /<caption class="sr-only">Hipotezler<\/caption>/);
    assert.equal((html.match(/<th scope="col"/g) ?? []).length, 7);
    assert.match(html, /<th scope="row"/);
  });

  it("says that a hypothesis was not run yet", () => {
    const html = render(<ResearchTable rows={[{ hypothesis: HYPOTHESIS, confirmation: null }]} />);
    assert.match(html, /çalışmadı/);
    assert.ok(!/Doğrulandı/.test(html));
  });

  it("translates the stage and keeps an unknown stage as it is", () => {
    assert.match(render(<ResearchTable rows={[{ hypothesis: { ...HYPOTHESIS, stage: "tuned" }, confirmation: null }]} />), /Ayarlı/);
    assert.match(render(<ResearchTable rows={[{ hypothesis: { ...HYPOTHESIS, stage: "stage9" }, confirmation: null }]} />), /stage9/);
  });

  it("explains that the exploration estimate is inflated", () => {
    assert.match(render(<ResearchTable rows={rows} />), /Yalnızca doğrulama etkisi güvenilirdir/);
  });

  it("marks a reversed result in its own words and speaks English", () => {
    const html = render(<ResearchTable rows={[{ hypothesis: HYPOTHESIS, confirmation: { ...CONFIRMATION, status: "reversed" } }]} />, "en");
    assert.match(html, /Reversed/);
    assert.match(html, /Adjusted p \(Holm\)/);
    assert.match(html, /\+0\.040/);
  });
});

describe("SessionDetails", () => {
  it("states the counts, the budget and the protocol in plain words", () => {
    const html = render(<SessionDetails detail={detail()} />);
    assert.match(html, /Araştırma oturumu real-1/);
    assert.match(html, /2 hipotez kaydedildi: 1 doğrulandı, 0 tersi çıktı, 1 doğrulanamadı, 0 test edilemedi\./);
    assert.match(html, /en çok 25 hipotezin hepsi birden/);
    assert.match(html, /1 keşif, 1 doğrulama veri seti/);
    assert.match(html, /Holm/);
    assert.match(html, /<table/);
  });

  it("names the models and the datasets with their plain names", () => {
    const html = render(<SessionDetails detail={detail()} />);
    assert.match(html, /Modeller: Random Forest, Lojistik regresyon/);
    assert.match(html, /Keşif:<\/span> Kredi riski/);
    assert.match(html, /Doğrulama:<\/span> Telekomünikasyon verisi/);
  });

  it("confirms the integrity of the registered hypotheses", () => {
    const html = render(<SessionDetails detail={detail()} />);
    assert.match(html, /Kayıtlı hipotezler, kayıttan beri değiştirilmedi\./);
    assert.ok(!/role="alert"/.test(html));
  });

  it("warns loudly when the integrity check fails", () => {
    const html = render(<SessionDetails detail={detail({ intact: false })} />);
    assert.match(html, /role="alert"/);
    assert.match(html, /sonuçlara güvenmeyin/);
    assert.ok(!/değiştirilmedi/.test(html));
  });

  it("shows the reason of a session that stopped early", () => {
    const html = render(<SessionDetails detail={detail({ summary: { ...SUMMARY, status: "aborted", reason: "only 2 of 6 exploration datasets finished" } })} />);
    assert.match(html, /Yarıda kaldı/);
    assert.match(html, /only 2 of 6 exploration datasets finished/);
  });

  it("hides the table when nothing was registered", () => {
    const html = render(<SessionDetails detail={detail({ session: { hypotheses: [], confirmations: [] } })} />);
    assert.ok(!/<table/.test(html));
  });

  it("lists the skipped proposals with their reason", () => {
    const skipped = [{ stage: "default", statement: "A beats B", reason: "already confirmed in an earlier session" }];
    const html = render(<SessionDetails detail={detail({ session: { hypotheses: [HYPOTHESIS], confirmations: [CONFIRMATION], skipped } })} />);
    assert.match(html, /Atlanan öneriler/);
    assert.match(html, /A beats B: already confirmed in an earlier session/);
  });

  it("speaks English", () => {
    const html = render(<SessionDetails detail={detail()} />, "en");
    assert.match(html, /Research session real-1/);
    assert.match(html, /2 hypotheses registered: 1 confirmed, 0 reversed, 1 not confirmed, 0 not testable\./);
  });
});

describe("SessionCards", () => {
  it("explains how to start a session when there is none", () => {
    assert.match(render(<SessionCards sessions={[]} />), /python -m app\.research run/);
  });

  it("links each session and shows its models, status and counts", () => {
    const html = render(<SessionCards sessions={[SUMMARY, { ...SUMMARY, id: "a b", status: "running" }]} />);
    assert.match(html, /href="\/research\/real-1"/);
    assert.match(html, /href="\/research\/a%20b"/);
    assert.match(html, /Tamamlandı/);
    assert.match(html, /Çalışıyor/);
    assert.match(html, /2 hipotez kaydedildi, 1 doğrulandı/);
    assert.match(html, /Modeller: Random Forest, Lojistik regresyon/);
  });
});
