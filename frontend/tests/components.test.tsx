import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ApprovalDialog } from "../components/ApprovalDialog.tsx";
import { ClaimCard } from "../components/ClaimCard.tsx";
import { CampaignBadge } from "../components/CampaignBadge.tsx";
import { CampaignControls } from "../components/CampaignControls.tsx";
import { ConfidenceMeter } from "../components/ConfidenceMeter.tsx";
import { DatasetChart } from "../components/DatasetChart.tsx";
import { ErrorNotice } from "../components/ErrorNotice.tsx";
import { LanguageProvider } from "../components/LanguageProvider.tsx";
import { LiveProgress } from "../components/LiveProgress.tsx";
import { ResearchStatus } from "../components/ResearchStatus.tsx";
import { SummaryView } from "../components/SummaryView.tsx";
import { Term } from "../components/Term.tsx";
import { ThemeToggle } from "../components/ThemeToggle.tsx";
import { VerdictBadge } from "../components/VerdictBadge.tsx";
import type { ExperimentSpec, PlainSummary, ResearchSnapshot, SummaryClaim } from "../lib/types.ts";

const CLAIM: SummaryClaim = {
  id: "C1",
  statement: "Trees beat nets",
  verdict: { code: "replicated", label: "Doğrulandı", tone: "positive", meaning: "İddia tutarlı biçimde doğru çıktı." },
  headline: "Random Forest, Yapay sinir ağı (MLP) modelinden daha iyi çıktı",
  confidence: { level: "high", label: "Yüksek güven", reason: "Tüm ölçütlerde aynı sonuç çıktı." },
  primary_metric: "roc_auc",
  datasets_for: 9,
  datasets_against: 0,
  datasets_total: 9,
  metrics: [{ metric: "roc_auc", label: "ROC-AUC", meaning: "Ayırma başarısı.", wins: 9, losses: 0, ties: 0, total: 9, median_difference: 0.0425, significant: true, testable: true }],
  chart: {
    metric: "roc_auc",
    metric_label: "ROC-AUC",
    subject_label: "Random Forest",
    other_label: "Yapay sinir ağı (MLP)",
    points: [
      { dataset: "tb_credit", label: "Kredi riski", subject: 0.85, other: 0.8 },
      { dataset: "tb_pol", label: "Telekomünikasyon verisi", subject: 0.9, other: 0.91 },
    ],
  },
};

const SUMMARY: PlainSummary = {
  language: "tr",
  campaign_id: "abc",
  title: "Ağaçlar sinir ağlarına karşı",
  source: null,
  status: { code: "completed", label: "Tamamlandı", tone: "positive" },
  progress: { finished: 9, failed: 0, total: 9, percent: 100 },
  live: { running: [], eta_seconds: null, cancel_requested: false },
  actions: { cancel: false, retry: false },
  recoveries: 0,
  headline: CLAIM.headline,
  verdict_counts: { replicated: 1 },
  claims: [CLAIM],
  ranking: [{ model: "RandomForest", label: "Random Forest", average_rank: 1.5, position: 1 }],
  method: ["9 gerçek veri setinde denendi."],
  cautions: ["Sonuçlar yalnızca denenen 9 veri seti için geçerlidir."],
  datasets: [{ key: "tb_credit", label: "Kredi riski" }],
  glossary: { dataset: { term: "Veri seti", explanation: "Gerçek bir veri tablosu." } },
  error: null,
  error_info: null,
};

function render(node: React.ReactNode, language: "tr" | "en" = "tr"): string {
  return renderToStaticMarkup(<LanguageProvider serverLanguage={language}>{node}</LanguageProvider>);
}

describe("VerdictBadge", () => {
  it("shows the label with the icon of its tone", () => {
    const html = render(<VerdictBadge label="Doğrulandı" tone="positive" />);
    assert.match(html, /Doğrulandı/);
    assert.match(html, /✓/);
    assert.match(html, /bg-accent-tint/);
  });

  it("uses another icon and colour for a refuted verdict", () => {
    const html = render(<VerdictBadge label="Çürütüldü" tone="negative" />);
    assert.match(html, /✕/);
    assert.match(html, /bg-danger-tint/);
  });

  it("falls back for an unknown tone", () => {
    assert.match(render(<VerdictBadge label="?" tone="strange" />), /bg-card/);
  });

  it("is larger when asked", () => {
    assert.match(render(<VerdictBadge label="x" tone="muted" large />), /text-base/);
    assert.match(render(<VerdictBadge label="x" tone="muted" />), /text-xs/);
  });
});

describe("ConfidenceMeter", () => {
  it("fills three segments for high confidence", () => {
    const html = render(<ConfidenceMeter confidence={CLAIM.confidence} />);
    assert.equal((html.match(/bg-accent/g) ?? []).length, 3);
    assert.match(html, /Yüksek güven/);
    assert.match(html, /Tüm ölçütlerde aynı sonuç çıktı\./);
  });

  it("fills one segment for low confidence", () => {
    const html = render(<ConfidenceMeter confidence={{ level: "low", label: "Düşük güven", reason: "Kanıt yok." }} />);
    assert.equal((html.match(/bg-dim/g) ?? []).length, 1);
    assert.equal((html.match(/bg-line-soft/g) ?? []).length, 2);
  });

  it("fills two segments for medium confidence", () => {
    const html = render(<ConfidenceMeter confidence={{ level: "medium", label: "Orta güven", reason: "x" }} />);
    assert.equal((html.match(/bg-warn/g) ?? []).length, 2);
  });
});

describe("DatasetChart", () => {
  it("lists every dataset with both scores in the language of the page", () => {
    const html = render(<DatasetChart chart={CLAIM.chart} />);
    assert.match(html, /Kredi riski/);
    assert.match(html, /0,850/);
    assert.match(html, /0,800/);
    assert.match(html, /Veri setlerine göre ROC-AUC \(yüksek iyidir\)/);
  });

  it("writes decimals with a point in English", () => {
    const html = render(<DatasetChart chart={CLAIM.chart} />, "en");
    assert.match(html, /0\.850/);
    assert.match(html, /ROC-AUC by dataset \(higher is better\)/);
  });

  it("names both sides in the legend", () => {
    const html = render(<DatasetChart chart={CLAIM.chart} />);
    assert.match(html, /Random Forest/);
    assert.match(html, /Yapay sinir ağı \(MLP\)/);
  });

  it("says where the bars start", () => {
    assert.match(render(<DatasetChart chart={CLAIM.chart} />), /Çubuklar 0,7 değerinden başlar\./);
  });

  it("bolds the winner of each dataset", () => {
    const html = render(<DatasetChart chart={CLAIM.chart} />);
    assert.match(html, /font-semibold text-ink">0,850</);
    assert.match(html, /font-semibold text-ink">0,910</);
  });
});

describe("ClaimCard", () => {
  it("shows the headline, the verdict, the dataset count and the confidence", () => {
    const html = render(<ClaimCard claim={CLAIM} />);
    assert.match(html, /Random Forest, Yapay sinir ağı \(MLP\) modelinden daha iyi çıktı/);
    assert.match(html, /Doğrulandı/);
    assert.match(html, /9 \/ 9/);
    assert.match(html, /Yüksek güven/);
    assert.match(html, /Üstün gelen veri seti/);
  });

  it("states the original claim sentence", () => {
    assert.match(render(<ClaimCard claim={CLAIM} />), /İddia:<\/span> Trees beat nets/);
  });

  it("counts the opposite datasets for a refuted claim", () => {
    const refuted = { ...CLAIM, verdict: { ...CLAIM.verdict, code: "contradicted", label: "Çürütüldü", tone: "negative" } };
    assert.match(render(<ClaimCard claim={refuted} />), /Tersinin üstün geldiği veri seti/);
  });

  it("keeps the numbers in a closed details block", () => {
    const html = render(<ClaimCard claim={CLAIM} />);
    assert.match(html, /<details[^>]*><summary[^>]*>Sayılar ve ayrıntılar<\/summary>/);
    assert.match(html, /9 \/ 9 veri setinde üstün/);
    assert.match(html, /\+0,0425/);
    assert.match(html, /İstatistiksel olarak anlamlı/);
  });

  it("marks a measure that could not be tested", () => {
    const claim = { ...CLAIM, metrics: [{ ...CLAIM.metrics[0], testable: false }] };
    assert.match(render(<ClaimCard claim={claim} />), /Test edilemedi/);
  });

  it("marks a measure that is not significant", () => {
    const claim = { ...CLAIM, metrics: [{ ...CLAIM.metrics[0], significant: false }] };
    assert.match(render(<ClaimCard claim={claim} />), /Anlamlı değil/);
  });

  it("folds into a summary line in compact mode and opens on request", () => {
    const closed = render(<ClaimCard claim={CLAIM} compact />);
    assert.match(closed, /<details class="group[^"]*">/);
    assert.ok(!/<details[^>]* open/.test(closed));
    assert.match(render(<ClaimCard claim={CLAIM} compact open />), /<details open=""/);
    assert.match(closed, /9 \/ 9/);
  });

  it("speaks English when the page does", () => {
    const html = render(<ClaimCard claim={{ ...CLAIM, verdict: { ...CLAIM.verdict, label: "Confirmed" } }} />, "en");
    assert.match(html, /Datasets where it came out ahead/);
    assert.match(html, /Numbers and details/);
    assert.match(html, /Claim:<\/span> Trees beat nets/);
  });
});

describe("SummaryView", () => {
  it("shows the claim, the method, the cautions, the ranking, the datasets and the glossary", () => {
    const html = render(<SummaryView summary={SUMMARY} />);
    assert.match(html, /Nasıl test ettik\?/);
    assert.match(html, /9 gerçek veri setinde denendi\./);
    assert.match(html, /Dikkat edilmesi gerekenler/);
    assert.match(html, /Genel sıralama/);
    assert.match(html, /Denenen veri setleri/);
    assert.match(html, /Terimler sözlüğü/);
    assert.match(html, /Gerçek bir veri tablosu\./);
  });

  it("shows a progress bar while no result exists", () => {
    const running = { ...SUMMARY, claims: [], status: { code: "running" as const, label: "Çalışıyor", tone: "neutral" }, progress: { finished: 3, failed: 0, total: 9, percent: 33 } };
    const html = render(<SummaryView summary={running} />);
    assert.match(html, /width:33%/);
    assert.match(html, /3 \/ 9 veri seti tamamlandı/);
    assert.match(html, /Deneyler sürüyor/);
    assert.ok(!/Nasıl test ettik/.test(html));
  });

  it("repeats the headline above several claims and folds them", () => {
    const many = { ...SUMMARY, headline: "4 iddia sınandı: 4 doğrulandı", claims: [CLAIM, { ...CLAIM, id: "C2" }, { ...CLAIM, id: "C3" }, { ...CLAIM, id: "C4" }] };
    const html = render(<SummaryView summary={many} />);
    assert.match(html, /4 iddia sınandı: 4 doğrulandı/);
    assert.equal((html.match(/<details [^>]*class="group/g) ?? []).length, 4);
    assert.equal((html.match(/<details open=""/g) ?? []).length, 1);
  });

  it("keeps a few claims open as full cards", () => {
    const html = render(<SummaryView summary={{ ...SUMMARY, claims: [CLAIM, { ...CLAIM, id: "C2" }] }} />);
    assert.equal((html.match(/<article/g) ?? []).length, 2);
  });
});

describe("ErrorNotice", () => {
  const info = { code: "openai_quota", title: "OpenAI kredisi bitmiş", message: "Servis isteği kabul etmedi.", hint: "Kredi ekleyin.", technical: "Error code: 429" };

  it("shows the title, the cause, the hint and a closed technical block", () => {
    const html = render(<ErrorNotice info={info} />);
    assert.match(html, /role="alert"/);
    assert.match(html, /OpenAI kredisi bitmiş/);
    assert.match(html, /Servis isteği kabul etmedi\./);
    assert.match(html, /Ne yapabilirsiniz\?<\/span> Kredi ekleyin\./);
    assert.match(html, /<details[^>]*><summary[^>]*>Teknik ayrıntı<\/summary>/);
    assert.match(html, /Error code: 429/);
  });

  it("falls back to a plain message", () => {
    const html = render(<ErrorNotice fallback="Bir şey oldu" />);
    assert.match(html, /Bir sorun oluştu/);
    assert.match(html, /Bir şey oldu/);
  });

  it("shows nothing without information", () => {
    assert.equal(render(<ErrorNotice />), "");
    assert.equal(render(<ErrorNotice info={null} />), "");
  });

  it("omits the technical block when there is no technical text", () => {
    assert.ok(!/Teknik ayrıntı/.test(render(<ErrorNotice info={{ ...info, technical: "" }} />)));
  });

  it("speaks English when the page does", () => {
    assert.match(render(<ErrorNotice info={info} />, "en"), /What can you do\?/);
  });
});

const RUNNING: PlainSummary = {
  ...SUMMARY,
  claims: [],
  status: { code: "running", label: "Çalışıyor", tone: "neutral" },
  progress: { finished: 3, failed: 0, total: 9, percent: 33 },
  live: { running: [{ key: "a", label: "Kredi riski" }, { key: "b", label: "Telekomünikasyon verisi" }], eta_seconds: 420, cancel_requested: false },
  actions: { cancel: true, retry: false },
};

describe("LiveProgress", () => {
  it("shows the bar, the count, the running datasets and the time left", () => {
    const html = render(<LiveProgress summary={RUNNING} />);
    assert.match(html, /width:33%/);
    assert.match(html, /3 \/ 9 veri seti tamamlandı/);
    assert.match(html, /Şu an çalışan veri setleri: Kredi riski, Telekomünikasyon verisi/);
    assert.match(html, /Tahmini kalan süre: yaklaşık 7 dakika/);
    assert.match(html, /Deneyler sürüyor/);
  });

  it("says under a minute for a short estimate", () => {
    const html = render(<LiveProgress summary={{ ...RUNNING, live: { ...RUNNING.live, eta_seconds: 40 } }} />);
    assert.match(html, /bir dakikadan az/);
  });

  it("explains that the estimate comes later", () => {
    const html = render(<LiveProgress summary={{ ...RUNNING, live: { ...RUNNING.live, eta_seconds: null } }} />);
    assert.match(html, /ilk veri seti bitince hesaplanır/);
  });

  it("shows no time estimate and no dataset list while queued", () => {
    const queued = { ...RUNNING, status: { code: "queued" as const, label: "Sırada", tone: "muted" }, live: { running: [], eta_seconds: null, cancel_requested: false } };
    const html = render(<LiveProgress summary={queued} />);
    assert.match(html, /Kampanya sırada bekliyor/);
    assert.ok(!/Tahmini kalan süre|hesaplanır|Şu an çalışan/.test(html));
  });

  it("speaks English", () => {
    const html = render(<LiveProgress summary={RUNNING} />, "en");
    assert.match(html, /Estimated time left: about 7 minutes/);
    assert.match(html, /Datasets running now: Kredi riski/);
  });
});

describe("CampaignControls", () => {
  const noop = () => undefined;

  it("offers a cancel button while the campaign is active", () => {
    const html = render(<CampaignControls summary={RUNNING} onDone={noop} />);
    assert.match(html, /Kampanyayı iptal et/);
    assert.ok(!/Yeniden başlat|alertdialog/.test(html));
  });

  it("only says that the cancel is pending once it was requested", () => {
    const html = render(<CampaignControls summary={{ ...RUNNING, live: { ...RUNNING.live, cancel_requested: true } }} onDone={noop} />);
    assert.match(html, /İptal isteniyor/);
    assert.ok(!/Kampanyayı iptal et/.test(html));
  });

  it("offers to start again after a failure or a cancel", () => {
    const failed = { ...RUNNING, status: { code: "failed" as const, label: "Başarısız", tone: "negative" }, actions: { cancel: false, retry: true } };
    const html = render(<CampaignControls summary={failed} onDone={noop} />);
    assert.match(html, /Yeniden başlat/);
    assert.match(html, /Aynı ayarlarla baştan çalıştırılır/);
    assert.ok(!/Kampanyayı iptal et/.test(html));
  });

  it("tells how often the campaign was started again", () => {
    assert.match(render(<CampaignControls summary={{ ...SUMMARY, recoveries: 2 }} onDone={noop} />), /2 kez yeniden başlatıldı/);
  });

  it("ignores a cancel request on a campaign that is not active", () => {
    const html = render(<CampaignControls summary={{ ...SUMMARY, recoveries: 1, live: { running: [], eta_seconds: null, cancel_requested: true } }} onDone={noop} />);
    assert.ok(!/İptal isteniyor/.test(html));
  });

  it("counts a single restart too", () => {
    assert.match(render(<CampaignControls summary={{ ...SUMMARY, recoveries: 1 }} onDone={noop} />), /1 kez yeniden başlatıldı/);
  });

  it("shows nothing for a finished campaign", () => {
    assert.equal(render(<CampaignControls summary={SUMMARY} onDone={noop} />), "");
  });

  it("speaks English", () => {
    assert.match(render(<CampaignControls summary={RUNNING} onDone={noop} />, "en"), /Cancel the campaign/);
  });
});

describe("SummaryView for a campaign that has no result", () => {
  it("shows the live progress while it runs", () => {
    assert.match(render(<SummaryView summary={RUNNING} />), /Tahmini kalan süre/);
  });

  it("does not claim that a cancelled campaign is running", () => {
    const html = render(<SummaryView summary={{ ...RUNNING, status: { code: "cancelled", label: "İptal edildi", tone: "muted" }, actions: { cancel: false, retry: true } }} />);
    assert.match(html, /iptal edildi, bu yüzden bir sonuç üretilmedi/);
    assert.ok(!/Deneyler sürüyor/.test(html));
  });

  it("does not claim that a failed campaign is running", () => {
    const html = render(<SummaryView summary={{ ...RUNNING, status: { code: "failed", label: "Başarısız", tone: "negative" } }} />);
    assert.match(html, /sonuç üretemeden durdu/);
    assert.ok(!/Deneyler sürüyor/.test(html));
  });
});

describe("CampaignBadge", () => {
  it("knows the cancelled state", () => {
    const html = render(<CampaignBadge status="cancelled" />);
    assert.match(html, /İptal edildi/);
    assert.match(html, /bg-stopped-tint/);
  });
});

describe("ThemeToggle", () => {
  it("offers the dark theme on a light page", () => {
    const html = render(<ThemeToggle serverTheme="light" />);
    assert.match(html, /aria-label="Koyu temaya geç"/);
    assert.match(html, /☾/);
  });

  it("offers the light theme on a dark page", () => {
    const html = render(<ThemeToggle serverTheme="dark" />);
    assert.match(html, /aria-label="Açık temaya geç"/);
    assert.match(html, /☀/);
  });

  it("speaks English", () => {
    assert.match(render(<ThemeToggle serverTheme="light" />, "en"), /Switch to the dark theme/);
  });
});

const SNAPSHOT: ResearchSnapshot = {
  thread_id: "t",
  status: "completed",
  next: [],
  active_step: "",
  hypotheses: [],
  experiment_specs: [],
  selected_hypothesis: 0,
  approval_status: "approved",
  verification_status: "Passed",
  verifier_feedback: "",
  instability: { unstable: false, std_threshold: 0.05, flagged: [] },
  research_status: "Completed",
  consistency_feedback: "",
  referee_notes: [],
  error: "",
  steps: [],
};

describe("ResearchStatus", () => {
  it("shows the three checks of a single experiment in Turkish", () => {
    const html = render(<ResearchStatus snapshot={SNAPSHOT} />);
    assert.match(html, /aria-label="Araştırma denetimleri"/);
    assert.match(html, /Doğrulama geçti/);
    assert.match(html, /İddialar sonuçlarla uyuşuyor/);
  });

  it("shows a failed verification with its feedback", () => {
    const html = render(<ResearchStatus snapshot={{ ...SNAPSHOT, verification_status: "Failed", verifier_feedback: "çıktı eksik", research_status: "" }} />);
    assert.match(html, /Doğrulama başarısız/);
    assert.match(html, /çıktı eksik/);
    assert.match(html, /İddia kontrolü bekleniyor/);
  });

  it("waits while nothing was checked", () => {
    assert.match(render(<ResearchStatus snapshot={{ ...SNAPSHOT, verification_status: "", research_status: "" }} />), /Doğrulama bekleniyor/);
  });

  it("warns about a high variance", () => {
    const unstable = { unstable: true, std_threshold: 0.05, flagged: [{ model: "MLP", metric: "f1", std: 0.1234 }] };
    const html = render(<ResearchStatus snapshot={{ ...SNAPSHOT, instability: unstable }} />);
    assert.match(html, /Bölmeler arasında yüksek değişkenlik \(eşik 0\.05\)/);
    assert.match(html, /MLP f1 std 0\.123/);
  });

  it("asks for a review after two rewrites", () => {
    const html = render(<ResearchStatus snapshot={{ ...SNAPSHOT, research_status: "NeedsReview", consistency_feedback: "sayı uyuşmuyor" }} />);
    assert.match(html, /İnceleme gerekli: iddia kontrolü iki yeniden yazımdan sonra da sorun buldu/);
    assert.match(html, /sayı uyuşmuyor/);
  });

  it("shows the campaign checks in campaign mode", () => {
    const html = render(<ResearchStatus snapshot={{ ...SNAPSHOT, mode: "campaign", campaign_status: "completed", campaign_mlflow_run_id: "abc123" }} />);
    assert.match(html, /Kampanya bitti ve raporu izlenebilirlik denetimini geçti/);
    assert.match(html, /MLflow koşusu abc123/);
    assert.match(html, /Rapor, kampanya kanıtlarıyla uyuşuyor/);
    assert.ok(!/Doğrulama/.test(html));
  });

  it("names a campaign that is still running with the plain status", () => {
    const html = render(<ResearchStatus snapshot={{ ...SNAPSHOT, mode: "campaign", campaign_status: "running", research_status: "" }} />);
    assert.match(html, /Kampanya: Çalışıyor/);
    assert.match(html, /Rapor denetimi bekleniyor/);
  });

  it("keeps an unknown campaign status as it is and says when none was collected", () => {
    assert.match(render(<ResearchStatus snapshot={{ ...SNAPSHOT, mode: "campaign", campaign_status: "strange", research_status: "" }} />), /Kampanya: strange/);
    assert.match(render(<ResearchStatus snapshot={{ ...SNAPSHOT, mode: "campaign", campaign_status: "", research_status: "" }} />), /Kampanya henüz toplanmadı/);
  });

  it("flags a campaign report that needs review", () => {
    const html = render(<ResearchStatus snapshot={{ ...SNAPSHOT, mode: "campaign", campaign_status: "needs_review", research_status: "NeedsReview" }} />);
    assert.match(html, /Kampanya bitti ama kendi rapor denetimi sorun buldu/);
    assert.match(html, /İnceleme gerekli: rapor denetimi iki yeniden yazımdan sonra da sorun buldu/);
  });

  it("lists the referee notes in a closed block", () => {
    const html = render(<ResearchStatus snapshot={{ ...SNAPSHOT, referee_notes: ["not bir", "not iki"] }} />);
    assert.match(html, /<details[^>]*><summary[^>]*>Hakem notları \(2\)/);
    assert.match(html, /not iki/);
  });

  it("lists a single referee note too and none when there are none", () => {
    assert.match(render(<ResearchStatus snapshot={{ ...SNAPSHOT, referee_notes: ["tek not"] }} />), /Hakem notları \(1\)/);
    assert.ok(!/Hakem notları/.test(render(<ResearchStatus snapshot={SNAPSHOT} />)));
  });

  it("speaks English", () => {
    assert.match(render(<ResearchStatus snapshot={SNAPSHOT} />, "en"), /Verification passed/);
  });
});

describe("ApprovalDialog", () => {
  const specs: ExperimentSpec[] = [{ statement: "s", models: ["a", "b"], dataset: "churn", params: { MLP: { alpha: 0.01 } } }, { statement: "t", models: ["a", "b"], dataset: "credit", params: {} }];
  const noop = () => undefined;

  it("asks which hypothesis to run, with the dataset and the parameters", () => {
    const html = render(<ApprovalDialog hypotheses={["Birinci", "İkinci"]} specs={specs} busy={false} onDecide={noop} />);
    assert.match(html, /Plan duraklatıldı/);
    assert.match(html, /Çalıştırılacak varsayımı seçin/);
    assert.match(html, /Yalnız seçtiğiniz varsayım test edilir\./);
    assert.match(html, /Veri seti: churn · MLP\.alpha = 0\.01/);
    assert.match(html, /Veri seti: credit · varsayılan parametreler/);
  });

  it("starts with nothing chosen and the approve button off", () => {
    const html = render(<ApprovalDialog hypotheses={["Birinci"]} specs={specs} busy={false} onDecide={noop} />);
    assert.match(html, /<button type="button" disabled=""[^>]*>Onayla<\/button>/);
    assert.match(html, /Reddet<\/button>/);
    assert.ok(!/checked=""/.test(html));
  });

  it("locks the form while a decision is being sent", () => {
    assert.match(render(<ApprovalDialog hypotheses={["Birinci"]} specs={specs} busy onDecide={noop} />), /<fieldset[^>]*disabled=""/);
  });

  it("speaks English", () => {
    const html = render(<ApprovalDialog hypotheses={["One"]} specs={specs} busy={false} onDecide={noop} />, "en");
    assert.match(html, /Choose the hypothesis to run/);
    assert.match(html, /Dataset: churn/);
  });
});

describe("Term", () => {
  const glossary = { dataset: { term: "Veri seti", explanation: "Gerçek bir veri tablosu." } };
  const withGlossary = (node: React.ReactNode) => renderToStaticMarkup(<LanguageProvider serverLanguage="tr" initialGlossary={glossary}>{node}</LanguageProvider>);

  it("keeps the visible words as the name of the button and describes it with the tooltip", () => {
    const html = withGlossary(<Term id="dataset">Üstün gelen veri seti</Term>);
    const described = /aria-describedby="([^"]+)"/.exec(html);
    assert.ok(described);
    assert.ok(html.includes(`id="${described[1]}"`));
    assert.ok(!/aria-label/.test(html));
    assert.match(html, /<button[^>]*>Üstün gelen veri seti<\/button>/);
    assert.match(html, /role="tooltip"/);
    assert.match(html, /Gerçek bir veri tablosu\./);
  });

  it("gives each term its own tooltip id", () => {
    const html = withGlossary(<><Term id="dataset">bir</Term><Term id="dataset">iki</Term></>);
    const ids = [...html.matchAll(/aria-describedby="([^"]+)"/g)].map((item) => item[1]);
    assert.equal(ids.length, 2);
    assert.notEqual(ids[0], ids[1]);
  });

  it("shows only the words when the glossary has no entry", () => {
    assert.equal(withGlossary(<Term id="unknown">kelime</Term>), "kelime");
    assert.equal(render(<Term id="dataset">kelime</Term>), "kelime");
  });
});
