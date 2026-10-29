# AxiomForge yol haritası

Bu dosya projenin durumunu, bilinen sınırlarını ve olası sonraki işleri özetler. Geliştirme tarihçesi ve ayrıntılı ölçüm kayıtları `docs/dev-notes/` altındadır.

## Durum

Planlanan kapsam tamam: iddia doğrulama hattı, çok veri setli kampanya motoru, istatistiksel karar katmanı, makale kapısı, TR/EN konsol ve araştırma ajanı katmanı (keşif / doğrulama ayrımı, dondurulmuş hipotezler, oturum boyu tek düzeltme). Backend, konsol ve tarayıcı testleri (axe erişilebilirlik taraması dahil) CI'da koşar; ölçümler `TECHNICAL_REPORT.md` içindedir.

| Alan | Durum |
| --- | --- |
| Erişim ve maliyet koruması (`API_KEY`, günlük başlatma sınırı) | Yapıldı |
| Yanlış pozitif oranının ölçümü (simülasyon ve gerçek modellerle null karşılaştırma) | Yapıldı |
| İşçi ölümünden kurtarma, iptal, yeniden başlatma | Yapıldı |
| Konsol: sade özet, grafik, sözlük, sebepli hata mesajları, koyu tema, TR/EN, klavye ve ekran okuyucu uyumu | Yapıldı |
| Araştırma ajanı: komut satırı ve konsoldan başlatma, canlı veri seti ilerlemesi | Yapıldı |
| Docker ile tek komutla kurulum, CI | Yapıldı |

## Bilinen sınırlar

- Yalnız ikili sınıflandırma ve tablo verisi; en çok 16 sayısal veri seti (bir benchmark ailesi).
- Literatür yalnız arXiv; planlayıcı özet ve sonuç bölümünü görür, tam metni değil. Çıktı yalnız Markdown.
- Küçük farklarda (ROC-AUC'de bir puanın altı) istatistiksel güç düşük; 10 doğrulama veri setinde en küçük p değeri 0,002.
- Ayar protokolü tek ayarlama kümesi ve küçük ayrık ızgaradır; iç içe çapraz doğrulama yoktur.
- Eski tek veri setli deney hattı ile kampanya hattı yan yana durur; birleştirilmedi.
- Araştırma ajanı yeni bilimsel bulgu iddia etmez; gerçek oturumunun sonucu (ağaç toplulukları tabloda sinir ağlarından iyi) literatürdeki bilinen bir bulguyu doğrular.
- Test koşuları Postgres ve `mlflow.db` içinde kalıntı bırakır; temizleme kararı sahibine aittir.

## Olası sonraki işler

- **Moderatör hipotezleri**: "üstünlük yüksek boyutlu veri setlerinde daha mı büyük?" türü hipotezler. Doğrulama kümesi alt kümeleri ve ayrı bir hata bütçesi gerekir.
- **Regresyon ve daha çok veri seti**: yeni metrik ve skor yönü gerektirir, doğrulama gücünü artırır.
- **İki hattın birleştirilmesi** (deney ve kampanya).
- **İç içe çapraz doğrulamalı ayar**: maliyeti yaklaşık 10 katına çıkarır ve önceki sonuçları değiştirir.
- **Üreticiler arası sistematik karşılaştırma**: `--reuse` ile aynı deney sonuçları üzerinde kural tabanlı ve dil modeli üreticileri, birden çok tohumla.
- **Kapı ölçümü**: 17 regex kapısından 14'ünün yanlış alarm oranı, bilerek bozulmuş etiketli makalelerle.

## İnsan gerektiren işler

- Üç-beş kişiyle denetimsiz kullanım gözlemi ("bu sayfa ne diyor?", "neye güvenebilirim?").
- Ekran okuyucuyla gerçek dinleme.
- Halka açık demo için bir sunucu (API anahtarı ve günlük sınır hazır).
