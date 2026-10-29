# AxiomForge yol haritası (26 Ekim 2026)

Bu dosya "projeyi bitirmek için ne kaldı" sorusunun cevabıdır. Yarın buradan devam edilir. Sıra önerisi en altta.

## 0. Bugünkü kullanıcı geri bildirimi (frontend'in ilk gerçek denemesi)

- Sistem çalışıyor: 9 veri setinde "ağaç tabanlı modeller daha iyi" sonucu görüldü ve doğru.
- **Ama sonuç sayfası kullanıcıya göre değil.** Kullanıcının sözü: "sayı cümbüşü", çok teknik, bağlamdan kopulabiliyor ("campaign nedir, tıkladığım yerde ne var anlamadım").
- **Hata mesajı yanıltıcıydı:** planlayıcı reddedince ekranda "kaynak yok" yazıyordu; gerçek sebep, bellekteki eski kampanyalar yüzünden modelin reddetmesiydi. Sebep düzeltildi (`e41ba4f`), ama kullanıcıya gösterilen metin sorunu duruyor.
- **Bellek kirliliği:** benchmark ve test amaçlı koşturulan kampanyalar, gerçek kullanıcı sorularının "geçmiş kampanyalar" listesine karışıyor.
- Karar bekleyen soru: **arayüzün hedef kullanıcısı kim?** (araştırmacı mı, öğrenci mi, sistemi yöneten biri mi?) Sadeleştirme buna göre yapılacak.

## A. Projeyi bitirmek için kalanlar (arka plan ve güvence)

### A1. Bitmiş saymadan önce
1. **Maliyet ve erişim koruması.** `/start_campaign` ve `/start_research` kimliksiz ve limitsiz; her çağrı E2B ve OpenAI parası harcıyor. En az bir API anahtarı ve günlük bütçe / hız sınırı. **[Yapıldı 27 Ekim: `app/guard.py`, isteğe bağlı `API_KEY` + günlük başlatma sınırı]**
2. **Gerçek sahte pozitif oranı.** Tohum-farklı özdeş iki modelle boş (null) karşılaştırma; bunun için protokolün `random_state`'ini parametreleştirmek gerekir. Yakın çiftler bunu ölçmez (bkz. `AUTONOMOUS_REPORT.md` Takip 5). **[27 Ekim, ikinci tur: gerçek modellerle tohum-farkı karşılaştırması `tools/null_seed.py` ile yapıldı, sonuç `AUTONOMOUS_REPORT.md` Takip 8'de]**
3. **Kapı yanlış alarm oranları.** 17 regex kapısının genel yanlış alarm oranı ölçülmedi; meta makale kapısı tek kampanya ve 10 örnekle ölçüldü. **[Yapıldı 27 Ekim, ikinci tur: meta makale kapısı ayarlı kıyasta 10/10, ayarsız kıyasta ilk taslakların 6/10'u işaretlendi (2 gerçek abartı, 3-4 zararsız 'not supported'); 17 regex kapısının tek tek yanlış alarm oranı hâlâ ölçülmedi, bu ölçüm etiketli bir taslak kümesi ister]]** **[27 Ekim, üçüncü tur: meta makale kapısındaki 'not supported' yanlış alarm sınıfı kaldırıldı (ilk taslak temizliği 4/10 -> 7/10); 17 regex kapısının tek tek yanlış alarm oranı hâlâ ölçülmedi]]**
4. **İşçi ölümünden kurtarma.** Deney hattında 30 dakika sessizlik yalnız `failed` olarak gösteriliyor; otomatik yeniden deneme yok. **[Yapıldı 27 Ekim, ikinci tur: kampanya görevi `acks_late` + `reject_on_worker_lost` ile yeniden teslim edilir (en çok 2 saat), bayat kampanya `failed` görünür, kullanıcı 'Yeniden başlat' ile bekletmeden başlatır; canlı işçi öldürme denemesi yapılmadı, deney (tek araştırma) hattında otomatik yeniden deneme yok]]** **[27 Ekim, üçüncü tur: tek araştırma hattı için `POST /research/{id}/retry` ve konsol düğmesi; kampanya görevinin yeniden teslimi Linux/Docker'da canlı işçi öldürülerek doğrulandı, Windows'ta Celery bunu yapmaz (elle 'Yeniden başlat')]]**

### A2. Büyük ihtimalle yapılacaklar
5. **Dağıtım:** frontend Docker'da değil; tek komutla ayağa kaldırma yok; gizli bilgi yönetimi `.env` düzeyinde. **[Yapıldı 27 Ekim: frontend Dockerfile + compose servisi; gizli bilgi yönetimi hâlâ `.env`]**
6. **Bellek ayrımı:** benchmark / test kampanyalarını kullanıcı belleğinden ayır (etiket ya da ayrı koleksiyon) ve temizleme yolu sun. **[Yapıldı 27 Ekim: kampanya `origin` etiketi, geçmişte test koşularını gizleme, `tools/memory_report.py`; ayrı koleksiyon yok]**
7. **Test kalıntıları** Postgres ve `mlflow.db` içinde duruyor; silme kararı kullanıcıda.
8. **İki paralel hat:** eski tek veri setli deney hattı ve kampanya hattı yan yana; birini emekli et ya da ayır. Küçük ölü kod kaldı (`EXPERIMENT_CSV_SCHEMA`).
9. **Ayar protokolü:** tek ayarlama kümesi, küçük ayrık ızgara; iç içe çapraz doğrulama yok. (MLP bulgusu bir artefaktmış, bkz. Takip 4.)

### A3. Kapsam sınırları (bitirmek için şart değil)
- Yalnız ikili sınıflandırma ve tablo verisi (regresyon, çok sınıf, metin, görüntü yok).
- 9 sayısal benchmark seti + birkaç çekirdek set; güç buna bağlı.
- Literatür yalnız arXiv; planlayıcı özet ve sonuç bölümünü görüyor, tam metni değil.
- Çıktı yalnız Markdown (PDF / LaTeX yok).

## B. Frontend ve ürün yenilemesi

Öncelik sırası yukarıdan aşağıya. Her madde için önce bir ekran taslağı çizilip onaylanmalı.

### B1. Dil ve içerik (en acil)
1. **Sonuç özeti kartı** sayfanın en üstünde: tek cümle ("Ağaç tabanlı modeller sinir ağından 9 veri setinin 9'unda daha iyi çıktı") + renkli karar rozeti + güven göstergesi. Sayısal ayrıntılar katlanır. **[Yapıldı 27 Ekim: `SummaryView`, `ClaimCard`]**
2. **Karar etiketleri sade dilde:** REPLICATED → "Doğrulandı", CONTRADICTED → "Çürütüldü (tersi doğru)", INCONCLUSIVE → "Kanıt yetersiz / fark yok", PARTIALLY → "Kısmen doğrulandı", NOT TESTABLE → "Test edilemedi". Renk ve simge ile. **[Yapıldı 27 Ekim: `vocabulary.py`]**
3. **Rapor katmanları:** Özet / Nasıl yaptık / Ayrıntılı sayılar / Kanıt defteri sekmeleri; tek uzun Markdown sayfası yerine. **[Yapıldı 27 Ekim: Özet / Ayrıntılı rapor / Kanıtlar sekmeleri]**
4. **Terim sözlüğü (ipucu balonları):** kampanya, iddia, veri seti, ROC-AUC, Wilcoxon, Holm, tuned, sandbox, `[E1]` kanıt numarası. **[Yapıldı 27 Ekim: `Term`, `GET /glossary`]**
5. **Anlamlı kampanya adları:** kimlik (`benchmark-default`) yerine iddia cümlesi; kimlik ikinci planda. **[Yapıldı 27 Ekim: iddia cümlesi başlıkta]**
6. **Hata mesajları kullanıcı dilinde ve sebepli:** planlayıcı reddi, OpenAI kotası, bayat işçi, sandbox hatası, geçersiz sorgu için ayrı mesaj ve "ne yapmalıyım" önerisi. Teknik ayrıntı "ayrıntıyı göster" arkasında. **[Yapıldı 27 Ekim: `friendly_errors.py`, `ErrorNotice`; tek deney hattı ekranları hariç]**
7. **Dil seçeneği (TR / EN):** özet ve etiketler için deterministik şablonlar (LLM çevirisi kapıları bozabilir); makale metninin dili ayrı bir karar. **[Yapıldı 27 Ekim: TR/EN deterministik şablonlar]**

### B2. Akış
8. **Ana sayfa:** "Ne yapar?" tek cümle + 3 hazır örnek soru düğmesi; modları sade adlandır ("Tek deney" / "Çok veri setli sınama"). **[Yapıldı 27 Ekim: hero, 3 adım, örnek sorular]**
9. **Onay penceresi:** üç planı karşılaştırma tablosu, süre ve tahmini maliyet ($), alıntıyı öne çıkarma, "bu ne anlama geliyor" yardım metni. **[Yapıldı 27 Ekim: sade plan kartları; tahmini maliyet ($) yok]**
10. **Canlı ilerleme:** tahmini kalan süre, hangi veri setinde olduğu, iptal düğmesi. **[Yapıldı 27 Ekim, ikinci tur: çalışan veri setleri, tahmini kalan süre ve iki adımlı iptal; iptal çalışan sandbox'ı kesmez]]**
11. **Gelişmiş ayarlar** katlanır bölümde: ayar (tuning), ayarlama payı, revision sabitleme. **[Yapıldı 27 Ekim, ikinci tur: ayrı bir bölüm yazılmadı: ayar ve yalnız-ROC-AUC seçenekleri zaten onay penceresindeki plan varyantlarıdır; ayarlama payı ve revision sabitleme yalnız komut satırında]]**
12. **Geçmiş:** arama / filtre, benchmark ve test kampanyalarını gizleme, arşivleme / silme, iki kampanyayı yan yana karşılaştırma. **[Yapıldı 27 Ekim: arama ve test koşularını gizleme; arşiv/silme ve yan yana karşılaştırma yok]**
13. **Dışa aktarma ve paylaşım:** Markdown / PDF indirme, paylaşılabilir bağlantı. **[Yapıldı 27 Ekim: Markdown indirme; PDF ve paylaşım bağlantısı yok]**

### B3. Görsel
14. **Grafikler:** veri seti başına model skorları (çubuk ya da ısı haritası), "9/9 veri setinde kazandı" şeridi, fark büyüklüğü. **[Yapıldı 27 Ekim: veri seti başına çubuk grafik]**
15. **Tasarım sistemi:** tutarlı tipografi, boşluk, koyu / açık tema, mobil uyum, erişilebilirlik (klavye, kontrast). **[27 Ekim, ikinci tur: koyu / açık tema (sistemi izler, elle değişir), adlandırılmış renk jetonları, kontrast ölçüldü; klavye ve ekran okuyucu denetimi yapılmadı]]** **[27 Ekim, üçüncü tur: klavye gezinmesi (ARIA sekmeler, odak halkası), axe ile WCAG A/AA taraması iki temada; ekran okuyucuyla gerçek dinleme yapılmadı]]**

### B4. Kalite
16. **Otomatik arayüz testi** (Playwright gibi) ve görsel regresyon; şimdi yalnız yardımcı fonksiyon testleri var. **[27 Ekim, ikinci tur: bileşenler sunucuda çizilerek test ediliyor ve 12 Playwright testi API'yi taklit ederek tarayıcıda koşuyor (CI'da ayrı iş, Linux konteynerinde doğrulandı); görsel regresyon yok]]**
17. **Kullanıcı gözlemi:** 3-5 kişiyle denetimsiz kullanım testi (sorular: "bu sayfa ne diyor?", "neye güvenebilirim?").

## C. Önerilen sıra
1. Hedef kullanıcıyı netleştir ve B1 + B2'nin ekran taslaklarını çiz (kod yazmadan).
2. B1 (özet kartı, etiketler, hata mesajları) + A2-6 (bellek ayrımı): en çok kullanıcı hissi değiştiren işler.
3. A1-1 (erişim koruması), A1-2 (null karşılaştırma): sistemi başkasına açmak ve "güvenilir" iddiasını ölçmek için.
4. B2, B3, sonra B4.
5. A2'nin kalanı ve A3 yalnız ihtiyaç doğarsa.

## D. Durum (28 Ekim, dördüncü tur sonu)
- Kod: 3720 pytest testi (3 atlandı), 190 frontend Node testi, 46 Playwright testi (işlev, axe erişilebilirlik, klavye, araştırma yeniden deneme, araştırma sayfaları). Üçüncü tura kadarki her şey push edildi (CI yeşil); dördüncü tur commitleri yerelde, push kullanıcının isteğine bağlı.
- Yapılanlar: B1, B2, B3, B4-16, A1-1, A1-2, A1-3 (meta makale kapısı), A1-4 (iki hat), A2-5, A2-6 ve **E4: araştırma ajanı** (bölüm E).
- Kalanlar: B4-17 kullanıcı gözlemi (insan gerekir), ekran okuyucuyla gerçek dinleme, 17 regex kapısından 14'ünün yanlış alarm oranı (örneklerde hiç ateşlemediler; bilerek bozulmuş etiketli makale ister), iki paralel hattın birleştirilmesi (A2-8), iç içe çapraz doğrulamalı ayar (A2-9), bölüm E5.
- Karar bekleyen: arayüzün asıl hedef kullanıcısı; veritabanındaki test kalıntılarının silinmesi (A2-7).
- Sunucuları açmak için komutlar `CONTINUATION.md` "Çalıştırma" bölümünde; konsol `http://localhost:3000`, ya da `docker compose up`.

## E. Konumlandırma ve "araştırma ajanı"na giden yol (27 Ekim 2026 sohbeti)

### E1. Şu an projenin dürüst tanımı
- Bugünkü sistem bir **iddia doğrulama / yeniden üretilebilirlik ajanıdır**: iddiayı makaleden çıkarır, 9 gerçek veri setinde sandbox'ta dener, kararı LLM'e değil istatistiğe (Wilcoxon, Holm, Friedman) bırakır, her sayıyı kanıt defterine bağlar. LLM yalnız planlar ve düz yazı yazar; yazı 17 kuralla denetlenir.
- **27 Ekim itibarıyla araştırma ajanı değildi** (yeni hipotez üretmez, sonuçtan sonraki adımı seçmez, tek turluktur); **28 Ekim'de araştırma ajanı katmanı eklendi (E4)**, bu madde doğrulama katmanının tarifidir. Kapsam: ikili sınıflandırma, tablo verisi, 9 veri seti. Ana sonuç (ağaçlar tabloda sinir ağlarını yener) 2022 Grinsztajn makalesinin tekrarıdır.
- Güçlü yanı: sahte pozitifi ölçmesi (simülasyonda %2,1; gerçek modellerle 45 testlenebilir etkide 0), bilinen iddialarda 10/10, yakın çiftlerde 0/6 çelişkili karar, sınırlarını kendisinin raporlaması.
- Commit sayısı bir ölçüt değildir; değerlendirenler README'nin ilk ekranına, çalışan demoya, testlere ve ölçümlerin dürüstlüğüne bakar.

### E2. CV'de anlatım (abartısız)
> AxiomForge: LLM ajanlı ML iddia doğrulama sistemi. Yayımlanmış makalelerdeki model karşılaştırma iddialarını çıkarıp 9 gerçek veri setinde sandbox'ta yeniden deneyen, kararı LLM'e değil istatistiğe (Wilcoxon, Holm, Friedman) bırakan çok ajanlı sistem (LangGraph, FastAPI, Celery, Next.js). Bilinen iddialarda 10/10, yakın model çiftlerinde 0/6 çelişkili karar; boş farkta sahte pozitif oranı simülasyonla (%2,1) ve gerçek modellerle ayrıca ölçüldü. 3000+ test, mutasyon denetimi, Docker, CI, Playwright ve axe erişilebilirlik testleri.

Kaçınılacak: "otonom araştırma yapan yapay zekâ", "bilimsel keşif", commit sayısı.

### E3. Yakın yapılacaklar (konumlandırma)
1. Kısa teknik rapor (3-4 sayfa): sorun, yöntem, ölçümler, sınırlar.
2. README'nin başına tek ekran özet ve ekran görüntüleri; 1-2 dakikalık demo videosu.
3. Halka açık demo (küçük sunucuda `docker compose up`; API anahtarı ve günlük sınır hazır).
4. 3-5 kişiyle kullanım gözlemi (insan gerekir).
5. Karşılaştırma: aynı soruyu düz GPT'ye sormak ile sistemin çıktısı yan yana.

### E4. Araştırma ajanına dönüşüm yolu (28 Ekim 2026: uygulandı, ayrıntı `RESEARCH_AGENT.md` ve `TECHNICAL_REPORT.md`)
Fark, **kapalı döngü**: sonuçtan yeni hipotez üretmek ve bunu istatistiksel güvenceyle yapmak. Aşamalar ve durumları:
1. **Kapalı döngü: yapıldı.** `app/research/` (protokol, üretici, oturum, komut satırı). Üretici yalnız keşif görünümünü okur; iki aşama (varsayılan, ayarlı) ve ayarlı aşamayı tetikleme kuralı var. Üretici kural tabanlı ya da dil modeli (`--generator llm`) olabilir.
2. **Uyarlamalı analizin güvencesi: yapıldı.** Veri setleri bir kez ve tohumlu bölünür (6 keşif, 10 doğrulama), hipotez önce dondurulup diske yazılır (SHA-256 özeti, `verify` komutu ile değişiklik denetimi), doğrulama tam bir kez, oturumdaki tüm hipotezler tek Holm düzeltmesinde (BH q de raporlanır), kayıt sayısı `⌈α·2ⁿ⁻¹⌉−1` ile sınırlı, doğrulama sonuçları üreticiye geri verilmez. 16 veri setlik havuz için 7 veri seti eklendi (`extended` grubu).
3. **Ajanın kendini ölçmesi: yapıldı (simülasyon) ve gerçek veride bir oturum.** `tools/planted_effects.py`: 16 modelde aile hatası protokolde %3, aynı veride seçip test eden ajanda %24, düzeltmesiz %89; protokolün bedeli güç (%47 karşı %96). `tools/llm_baseline.py`: veri görmeyen dil modeli ile karşılaştırma. Gerçek oturum sonuçları `TECHNICAL_REPORT.md` bölüm 6.
4. **Yenilik denetimi: kısmen.** Oturum içi tekrar ve önceki oturumlarda doğrulanmış iddialar atlanır (nedeni kayda yazılır); literatür tam metnine bakan yenilik denetimi yok.
5. **Kapsam genişletme: yapılmadı** (regresyon, çok sınıf, model karşılaştırması dışı hipotez türleri, veri özelliği / moderatör hipotezleri).
6. **Dürüst beklenti** değişmedi: sonuç "yeni bilimsel keşif yapan ajan" değil, "istatistiksel güvenceli, kendini ölçen keşifsel analiz ajanı"dır.

### E5. Araştırma ajanı için sıradaki işler
- Moderatör hipotezleri ("üstünlük yüksek boyutlu veri setlerinde daha mı büyük?"): `moderators.py` hazır, doğrulama kümesi alt kümeleri ve ayrı bir bütçe gerekir.
- ~~Konsoldan oturum başlatma ve canlı ilerleme~~ **yapıldı (28 Ekim)**: `/research` sayfasındaki form (model seçimi, ayarlı aşama, üretici), `POST /start_research_session`, iptal ve yeniden başlatma, aşama metni ve 5 saniyelik yenileme; ölü işçi bayat olarak `failed` görünür. Canlı denendi: başlat, iptal, yeniden başlat, tamamlandı. Veri seti bazında ilerleme (bitenler, çubuk, şu an çalışanlar) de yapıldı (29 Ekim).
- Daha çok veri seti (regresyon dahil) ile doğrulama gücünü artırmak: 10 veri setinde en küçük p 0,002; 13 hipotezden sonra Holm ile hiçbiri anlamlı olamaz.
- Üreticiler arası sistematik karşılaştırma: `--reuse` ile aynı sonuçlar üzerinde kural, dil modeli ve (varsa) başka üreticiler, birden çok tohumla.
- Kullanıcı gözlemi (insan gerekir) ve halka açık demo.
