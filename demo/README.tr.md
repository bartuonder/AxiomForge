# Demo: API anahtarı olmadan gerçek sonuçları gezin

Bu klasör **AxiomForge'un gerçek çıktısını** taşır. OpenAI ya da E2B anahtarı, veritabanı ve herhangi bir harcama olmadan konsolu açıp gezebilirsiniz.

[English](README.md)

| Ne | Nerede | Ne göreceksiniz |
| --- | --- | --- |
| Araştırma ajanı oturumu `real-2` | `data/research/real-2/` | Altı keşif veri setine bakarak önerilen 16 hipotez, on mühürlü veri setinde birer kez sınandı: 15 doğrulandı, 0 tersi çıktı, 1 doğrulanamadı; keşif tahmini doğrulama etkisinin yanında |
| Replikasyon kampanyası "Ağaç tabanlı modeller sinir ağlarına karşı" | `data/campaigns/g-21bf5f449bb26c00fc824d40ed83aaf5/` | Tek iddia, 9 veri seti: karar, güven, veri seti başına grafik, kanıt defteri, rapor |
| Makaleden kampanya (Grinsztajn ve ark., 2022) | `data/campaigns/demo-grinsztajn-1/` | arXiv 2207.08815'ten iki iddia ve kaynakla karşılaştırma |

Bu dosyalardaki her sayıyı sistem sandbox koşusunda üretti. Oturumlar elle değiştirilmedi; `python -m app.research verify real-2` kayıtlı hipotezlerin değişmediğini doğrular.

## Yerelde çalıştırma (anahtar gerekmez)

Python 3.12 ve Node 24 gerekir (CI'ın kullandığı sürümler).

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
bash demo/load.sh                                # Windows: powershell -File demo/load.ps1
.venv/bin/uvicorn app.main:app --port 8000
```

İkinci bir terminalde:

```bash
cd frontend
npm install
npm run dev
```

`http://localhost:3000` adresini açın (`127.0.0.1` değil, `localhost`) ve şunlara bakın:

- **Geçmiş çalışmalar**: kampanyalar; özet, ayrıntılı rapor ve kanıtlar sekmesi. Makale kampanyası kıyas çalışması sayılır; görmek için "Test ve kıyas çalışmalarını da göster" kutusunu işaretleyin.
- **Araştırma ajanı**: `real-2` oturumu; protokol sade anlatımla, hipotez tablosu, bütünlük denetimi ve rapor indirme.

Yeni iş başlatan sayfalar (soru kutusu ve "Oturumu başlat" formu) tüm yığını ve kendi anahtarlarınızı ister; ana [README](../README.tr.md) dosyasına bakın.

## Docker ile

```bash
docker compose up -d --build
docker compose cp demo/data/research/. api:/srv/reports/research/
docker compose cp demo/data/campaigns/. api:/srv/reports/campaigns/
```

Sonra `http://localhost:3000` adresini açın.

## Dosyaları doğrudan okuma

```bash
python -m app.research verify real-2          # load.sh ile kopyalanan veri gerekir
python -m app.research show real-2            # oturum raporu
```

Kampanya raporları düz Markdown'dır: `data/campaigns/*/report.md`. İçlerindeki her sayı `ledger.json` içindeki bir kayda `[E#]` ile bağlanır (veri seti revision'ı, satır sayısı, kütüphane sürümleri, betik özeti). Sandbox'ta çalışan betikler `scripts/` içindedir.

## Bilinmesi gerekenler

- Veri 28 Ekim 2026'da, defterlerde yazılı veri seti ve kütüphane sürümleriyle üretildi. Yeni koşular biraz farklı çıkabilir.
- Demoyu `reports/` içine kopyalamak, araştırma ajanının `real-2` oturumunda zaten doğrulanmış iddiaları (ağaç toplulukları lojistik regresyondan ve MLP'den iyi) atlamasına yol açar. Kapatmak için `--no-history` kullanın.
- `reports/` git'te izlenmez; kimlik çakışmadıkça demo kendi sonuçlarınıza dokunmaz.
