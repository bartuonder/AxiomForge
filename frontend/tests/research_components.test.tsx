import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { LanguageProvider } from "../components/LanguageProvider.tsx";
import { ResearchTable } from "../components/ResearchTable.tsx";
import { SessionCards } from "../components/SessionList.tsx";
import { SessionControls } from "../components/SessionControls.tsx";
import { StartForm } from "../components/StartSession.tsx";
import { SessionDetails } from "../components/SessionView.tsx";
import { DEFAULT_RESEARCH_MODELS } from "../lib/researchView.ts";
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

describe("SessionDetails of a session that is not finished", () => {
  const queued = detail({ summary: { ...SUMMARY, status: "queued", registered: 0 }, session: { hypotheses: [] } });

  it("tells that a queued session waits and hides the result", () => {
    const html = render(<SessionDetails detail={queued} />);
    assert.match(html, /Sırada/);
    assert.match(html, /bir işçi süreci bekleniyor/);
    assert.ok(!/hipotez kaydedildi:/.test(html));
  });

  it("names the stage that runs", () => {
    const html = render(<SessionDetails detail={detail({ summary: { ...SUMMARY, status: "running", phase: "tuned" } })} />);
    assert.match(html, /Ayarlı aşamanın deneyleri çalışıyor/);
    const english = render(<SessionDetails detail={detail({ summary: { ...SUMMARY, status: "running", phase: "default" } })} />, "en");
    assert.match(english, /default-settings experiments are running/);
  });

  it("explains a dead worker", () => {
    const html = render(<SessionDetails detail={detail({ summary: { ...SUMMARY, status: "failed", reason: "the worker stopped" }, session: { hypotheses: [], stale: true } })} />);
    assert.match(html, /işçi süreci yanıt vermeyi kesti/);
    assert.match(html, /Başarısız/);
  });

  it("shows no phase once the session is finished", () => {
    assert.ok(!/deneyler çalışıyor/.test(render(<SessionDetails detail={detail()} />)));
  });
});

describe("SessionControls", () => {
  const controls = (status: string, cancelRequested = false) => render(<SessionControls sessionId="r-1" status={status} cancelRequested={cancelRequested} onDone={() => undefined} />);

  it("offers to cancel a session that is queued or running", () => {
    for (const status of ["queued", "running"]) {
      assert.match(controls(status), /Oturumu iptal et/);
    }
  });

  it("says that the cancel was asked and drops the button", () => {
    const html = controls("running", true);
    assert.match(html, /İptal isteniyor/);
    assert.ok(!/Oturumu iptal et/.test(html));
  });

  it("offers to start again after a failure, a cancel or an early stop", () => {
    for (const status of ["failed", "cancelled", "aborted"]) {
      const html = controls(status);
      assert.match(html, /Yeniden başlat/);
      assert.match(html, /Günlük başlatma sınırınızdan bir hak düşer/);
      assert.ok(!/Oturumu iptal et/.test(html));
    }
  });

  it("renders nothing for a completed session", () => {
    assert.equal(controls("completed"), "");
  });
});

describe("StartForm", () => {
  const form = (models: string[], extra: { busy?: boolean; error?: string; tuned?: boolean } = {}, language: "tr" | "en" = "tr") =>
    render(<StartForm choices={{ models, tuned: extra.tuned ?? false, generator: "rules" }} busy={extra.busy ?? false} error={extra.error ?? ""} onChange={() => undefined} onSubmit={() => undefined} />, language);

  it("lists the models with plain names and checks the chosen ones", () => {
    const html = form(DEFAULT_RESEARCH_MODELS);
    assert.match(html, /Random Forest/);
    assert.equal((html.match(/type="checkbox"/g) ?? []).length, 18);
    assert.equal((html.match(/checked=""/g) ?? []).length, 7);
  });

  it("explains the time and the cost before the start", () => {
    const html = form(DEFAULT_RESEARCH_MODELS);
    assert.match(html, /yaklaşık 20 dakika/);
    assert.match(html, /Günlük başlatma sınırınızdan bir hak düşer/);
    assert.match(html, /Ayarlı aşamayı da çalıştır \(her modele 12 ayar denemesi\)/);
  });

  it("disables the start button with fewer than two models and says why", () => {
    const html = form(["RandomForest"]);
    assert.match(html, /<button type="submit" disabled=""/);
    assert.match(html, /en az iki model seçin/);
    assert.ok(!/<button type="submit" disabled=""/.test(form(["RandomForest", "MLP"])));
    assert.ok(!/en az iki model seçin/.test(form(["RandomForest", "MLP"])));
  });

  it("disables everything while the request is sent", () => {
    const html = form(DEFAULT_RESEARCH_MODELS, { busy: true });
    assert.match(html, /Başlatılıyor…/);
    assert.match(html, /<fieldset[^>]*disabled=""/);
  });

  it("shows an error as an alert", () => {
    const html = form(DEFAULT_RESEARCH_MODELS, { error: "Günlük sınıra ulaşıldı" });
    assert.match(html, /role="alert"[^>]*>Günlük sınıra ulaşıldı/);
  });

  it("speaks English", () => {
    const html = form(DEFAULT_RESEARCH_MODELS, {}, "en");
    assert.match(html, /Start a new session/);
    assert.match(html, /Start the session/);
  });
});
