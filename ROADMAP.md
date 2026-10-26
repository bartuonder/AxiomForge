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
1. **Maliyet ve erişim koruması.** `/start_campaign` ve `/start_research` kimliksiz ve limitsiz; her çağrı E2B ve OpenAI parası harcıyor. En az bir API anahtarı ve günlük bütçe / hız sınırı.
2. **Gerçek sahte pozitif oranı.** Tohum-farklı özdeş iki modelle boş (null) karşılaştırma; bunun için protokolün `random_state`'ini parametreleştirmek gerekir. Yakın çiftler bunu ölçmez (bkz. `AUTONOMOUS_REPORT.md` Takip 5).
3. **Kapı yanlış alarm oranları.** 17 regex kapısının genel yanlış alarm oranı ölçülmedi; meta makale kapısı tek kampanya ve 10 örnekle ölçüldü.
4. **İşçi ölümünden kurtarma.** Deney hattında 30 dakika sessizlik yalnız `failed` olarak gösteriliyor; otomatik yeniden deneme yok.

### A2. Büyük ihtimalle yapılacaklar
5. **Dağıtım:** frontend Docker'da değil; tek komutla ayağa kaldırma yok; gizli bilgi yönetimi `.env` düzeyinde.
6. **Bellek ayrımı:** benchmark / test kampanyalarını kullanıcı belleğinden ayır (etiket ya da ayrı koleksiyon) ve temizleme yolu sun.
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
1. **Sonuç özeti kartı** sayfanın en üstünde: tek cümle ("Ağaç tabanlı modeller sinir ağından 9 veri setinin 9'unda daha iyi çıktı") + renkli karar rozeti + güven göstergesi. Sayısal ayrıntılar katlanır.
2. **Karar etiketleri sade dilde:** REPLICATED → "Doğrulandı", CONTRADICTED → "Çürütüldü (tersi doğru)", INCONCLUSIVE → "Kanıt yetersiz / fark yok", PARTIALLY → "Kısmen doğrulandı", NOT TESTABLE → "Test edilemedi". Renk ve simge ile.
3. **Rapor katmanları:** Özet / Nasıl yaptık / Ayrıntılı sayılar / Kanıt defteri sekmeleri; tek uzun Markdown sayfası yerine.
4. **Terim sözlüğü (ipucu balonları):** kampanya, iddia, veri seti, ROC-AUC, Wilcoxon, Holm, tuned, sandbox, `[E1]` kanıt numarası.
5. **Anlamlı kampanya adları:** kimlik (`benchmark-default`) yerine iddia cümlesi; kimlik ikinci planda.
6. **Hata mesajları kullanıcı dilinde ve sebepli:** planlayıcı reddi, OpenAI kotası, bayat işçi, sandbox hatası, geçersiz sorgu için ayrı mesaj ve "ne yapmalıyım" önerisi. Teknik ayrıntı "ayrıntıyı göster" arkasında.
7. **Dil seçeneği (TR / EN):** özet ve etiketler için deterministik şablonlar (LLM çevirisi kapıları bozabilir); makale metninin dili ayrı bir karar.

### B2. Akış
8. **Ana sayfa:** "Ne yapar?" tek cümle + 3 hazır örnek soru düğmesi; modları sade adlandır ("Tek deney" / "Çok veri setli sınama").
9. **Onay penceresi:** üç planı karşılaştırma tablosu, süre ve tahmini maliyet ($), alıntıyı öne çıkarma, "bu ne anlama geliyor" yardım metni.
10. **Canlı ilerleme:** tahmini kalan süre, hangi veri setinde olduğu, iptal düğmesi.
11. **Gelişmiş ayarlar** katlanır bölümde: ayar (tuning), ayarlama payı, revision sabitleme.
12. **Geçmiş:** arama / filtre, benchmark ve test kampanyalarını gizleme, arşivleme / silme, iki kampanyayı yan yana karşılaştırma.
13. **Dışa aktarma ve paylaşım:** Markdown / PDF indirme, paylaşılabilir bağlantı.

### B3. Görsel
14. **Grafikler:** veri seti başına model skorları (çubuk ya da ısı haritası), "9/9 veri setinde kazandı" şeridi, fark büyüklüğü.
15. **Tasarım sistemi:** tutarlı tipografi, boşluk, koyu / açık tema, mobil uyum, erişilebilirlik (klavye, kontrast).

### B4. Kalite
16. **Otomatik arayüz testi** (Playwright gibi) ve görsel regresyon; şimdi yalnız yardımcı fonksiyon testleri var.
17. **Kullanıcı gözlemi:** 3-5 kişiyle denetimsiz kullanım testi (sorular: "bu sayfa ne diyor?", "neye güvenebilirim?").

## C. Önerilen sıra
1. Hedef kullanıcıyı netleştir ve B1 + B2'nin ekran taslaklarını çiz (kod yazmadan).
2. B1 (özet kartı, etiketler, hata mesajları) + A2-6 (bellek ayrımı): en çok kullanıcı hissi değiştiren işler.
3. A1-1 (erişim koruması), A1-2 (null karşılaştırma): sistemi başkasına açmak ve "güvenilir" iddiasını ölçmek için.
4. B2, B3, sonra B4.
5. A2'nin kalanı ve A3 yalnız ihtiyaç doğarsa.

## D. Durum (yarın başlarken)
- Kod: 2681 pytest testi, 10 frontend Node testi, CI GitHub'da yeşil.
- Canlı doğrulanmış: kampanya motoru, ayar, istatistik, planlayıcı, hakem, MLflow, revision sabitleme, arXiv alımı.
- Ayrıntılı ölçümler: `AUTONOMOUS_REPORT.md`. Kod haritası ve dersler: `AI_CONTEXT.md` (3.15, 3.16). Kurallar: `CONTINUATION.md`.
- Sunucuları açmak için komutlar `CONTINUATION.md` "Çalıştırma" bölümünde; konsol `http://localhost:3000`.
