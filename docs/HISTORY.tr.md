# AxiomForge nasıl geliştirildi

[English](HISTORY.md) · [README'ye dön](../README.tr.md)

AxiomForge 10-29 Ekim 2026 arasında (yaklaşık 490 commit) katman katman büyüdü. Her katman, bir öncekinin açığa çıkardığı bir zayıflığı kapattı; bu zayıflıklar çoğunlukla kod okuyarak değil, gerçek sistemi çalıştırarak bulundu. Bu sayfa hikâyeyi kısaca anlatır; ayrıntılı notlar [`dev-notes/`](dev-notes/) altındadır.

## Fazlar

| Faz | Eklenen | Neden gerekti |
| --- | --- | --- |
| 1. Deney döngüsü | Bir model scikit-learn deneyi yazar, E2B sandbox'ında çalıştırır ve hata izinden kendi kodunu düzeltir (en çok 3 deneme). Sonuçlar MLflow'a gider. | Uçtan uca çalışan en basit şey. |
| 2. Ajan grafı | LangGraph hattı: literatür araması, üç plan önerisi, **insan onayı**, sonra deney. Durum PostgreSQL'de tutulur. | Bir insan onaylamadan hiçbir şey para harcamamalı ya da kod çalıştırmamalı. |
| 2.5. Deney hafızası | Geçmiş deneyler `pgvector` içine gömülür; planlayıcı önceki başarısızlıkları okur ve tekrar etmez. | Ajan aynı bozuk fikri önermeye devam ediyordu. |
| 3. Doğrulayıcı ve eleştiri döngüsü | Kod veri sızıntısı için incelenir; başarısız sonuç eleştiriyle deney adımına döner (en çok iki kez). | Geçen bir betik geçerli bir deney demek değildir. |
| 4. Rapor ajanı ve konsol | Atölye makalesi yazılır; bir Next.js konsolu koşuyu canlı gösterir. | Sonuçların okunabilir olması gerekir. |
| 5-7. Bilimsel sıkılık | Modeller aynı bölmede karşılaştırılır, dengesiz veri hesaba katılır, sonuç bölme tohumlarında ortalanır, koşu başına tek veri yüklemesi ve yalıtılmış durum. | Tek bir bölme bir anekdottur. |
| 8-9. İstatistiksel karar ve kontrol grubu | Karar dil modelinden Python'a alındı: tohumlar üzerinde eşleştirilmiş testler, Holm düzeltmesi; ayarlanan her model ayrıca kütüphane varsayılanıyla koşar (`Model__default`). | "Ayar işe yaradı" iddiası ayarsız bir kontrole karşı ölçülmeli. |
| 10. Gerçek veri | Sentetik veri bırakıldı. Gerçek Hugging Face veri setleri, doğrulanmış bir veri bloğuyla ve yalnız eğitim bölümüne uydurulan ön işlemeyle yüklenir. | Sentetik veri gerçek davranış hakkında bir şey kanıtlamaz. |
| 11. Makale kapısı | Deterministik kurallar abartıyı ve uydurma yöntemi reddeder; kilit cümleleri Python üretir, yazıcı kopyalar. | Canlı koşular yazıcının aynı hataları tekrarladığını gösterdi. |
| 12. Replikasyon kampanyası | **Dil modeli olmayan** bir motor yayımlanmış bir iddiayı çok veri setinde sınar: veri seti başına skor, veri setleri üzerinde Wilcoxon, Holm, Friedman, kanıt defteri ve her sayısı deftere bağlı rapor. | Tek veri seti bir iddiayı yeniden üretemez. |
| 13. Ajanlı kampanyalar | Graf, bir sorudan ya da arXiv makalesinden kampanya planlayabilir, onay ister, çalıştırır ve meta makale yazar; mod her zaman açıkça seçilir. | Motoru ajanlara, bir modele harcama yetkisi vermeden bağlamak. |
| 14. Kampanya genişletmeleri | Tekrarlanabilirlik künyesi (veri seti revision'ı, kütüphane sürümleri, belirtim özeti), moderatör analizi, varsayılan kontrollü ayarlı protokol, arXiv girişi ve bilinen 10 iddialık kıyas (10/10 doğru). | Sonuçları tekrarlanabilir kılmak ve sistemin kendisini ölçmek. |
| 15. Herkes için konsol | Sade özet, güven göstergesi, grafikler, sözlük, Türkçe ve İngilizce, koyu tema, anlaşılır hata kutuları, erişim anahtarı ve günlük sınır, iptal ve yeniden başlatma, klavye ve ekran okuyucu desteği, tarayıcı testleri, CI. | İlk gerçek kullanıcı denemesinin geri bildirimi: "sayı cümbüşü". |
| 16. Araştırma ajanı | Sonuçlardan kendi hipotezlerini, sahte keşifleri şişirmeden öneren kapalı döngü: keşif ve doğrulama veri setleri, dondurulmuş kayıtlı hipotezler, oturum başına tek düzeltme. Konsoldan başlatma, iptal, yeniden başlatma ve canlı ilerleme. | Verilen iddiaları doğrulamaktan yeni iddia önermeye, istatistiksel güvenceyle geçmek. Bkz. [`RESEARCH_AGENT.md`](../RESEARCH_AGENT.md). |

## Gerçek koşuların öğrettikleri

Belirleyici düzeltmelerin çoğu geçen testlerden değil, sistemi gerçekten çalıştırmaktan geldi:

- **Hakem dil modeli olmamalı.** Dil modeli hakem yeniden yazım döngüsünü kararsız yaptı; deterministik kontroller ve hazır cümleler güvenilirdi.
- **Kurallar çelişebilir.** İki makale kuralı (lideri iki bölümde yaz, hiçbir cümleyi tekrarlama) birlikte temiz bir makaleyi imkânsız kıldı; cümleler bilerek farklı yapıldı.
- **Bir kural doğru metne de ateşleyebilir.** "Was not supported" ifadesi "supported" kuralını tetikliyordu; olumsuzlama artık anlaşılıyor.
- **Bir ağ kopması oturumu öldürmemeli.** Bir sandbox bağlantısı koptu ve 17 dakikalık bir araştırma oturumu bitti, çünkü o istisna türü başarısız deneme sayılmıyordu. Artık bir denemenin her istisnası tek bir başarısız deneme sayılır.
- **İptal yarım aşamayı kaydetmemeli.** Canlı bir koşu, iptal edilen aşamanın yarım sonuçlarının diske yazıldığını ve yeniden başlatmanın bunları tam sayacağını gösterdi.
- **Bir dil modeli kendiyle çelişebilir.** Araştırma ajanının ilk isteminde hipotezlerin yaklaşık yarısı modelleri yanlış sırayla yazdı; protokol bunları keşif değil, tersi çıkan ya da doğrulanamayan olarak saydı ve istem düzeltildi.
- **Sistemi ölçün.** Karar katmanının sahte pozitif oranı (simülasyonda %2,1, gerçek modellerle 45'te 0) ve araştırma protokolünün oranı (%3; saf uyarlamalı bir ajanda %24) depodaki araçlarla ölçülür; bkz. [teknik rapor](../TECHNICAL_REPORT.md).

## Nasıl geliştirildi

- Özellikler önce testle yazıldı, sonra **mutasyon denetiminden** geçti: kod bilerek bozulur ve bir testin başarısız olması gerekir.
- Her özellik ya da düzeltme ayrı commit; belgeler ayrı commit.
- Gerçek LLM ve sandbox koşuları pahalıdır; testler bunlara hiç gitmez, gerçek koşular bilinçli yapıldı ve kaydedildi.
- Proje bir yapay zeka kodlama asistanıyla geliştirildi; devir notlarını [`dev-notes/`](dev-notes/) altında o tuttu. Tasarım kararları, ölçümler ve sınırlar kontrol edilebilsin diye belgelenmiştir.
