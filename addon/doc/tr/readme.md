# Kelime Tahmincisi - Proaktif Kelime Tahmini için NVDA Eklentisi

Yazdıklarınızı izleyen ve n-gram analizini kullanarak bir sonraki kelimeyi tahmin eden bir NVDA eklentisi. Tahminler NVDA'nın kendi konuşma motoru aracılığıyla duyurulur ve klavye kısayollarıyla kabul edilebilir.

## Bunun Neden Var Olduğunu

Lightkey Pro AT gibi mevcut kelime tahmin araçları, NVDA ile kullanıldığında önemli erişilebilirlik engellerine sahiptir:

- Hareketler NVDA komutlarıyla çakışıyor
- Sistem çapında tahmin, fare tıklamasını gerektirir
- NVDA'nın yanına yapıştırıldığında kelimeler karışıyor

Bu eklenti, NVDA'nın kendi içinde çalışarak bu sorunları çözer. Harici TTS yok, panoya yapıştırma yok, fare gerekmiyor. Tahminler NVDA'nın konuşma motoru aracılığıyla konuşulur ve doğrudan NVDA'nın klavye giriş sistemi aracılığıyla eklenir.

## Özellikler

- **Proaktif tahmin:** Bir kelimeyi tamamladıktan sonra (boşluğa veya noktalama işaretine basın), NVDA tahmin edilen sonraki 5 kelimeye kadar duyuru yapar.
- **Kısmi kelime tahmini:** Bir kelimenin bir kısmını yazın ve yazdıklarınızı tamamlayan öneriler almak için NVDA+Alt+O tuşlarına basın.
- **Sesli uyarı:** Tahminler duyurulmadan önce kısa bir bip sesi duyulur (yapılandırılabilir).
- **Klavye seçimi:** Bir tahmini kabul etmek için 1-5 tuşlarına basın. Kelime otomatik olarak yazılır.
- **Yazdıklarınızdan öğrenir:** N-gram modeli siz yazdıkça gerçek zamanlı olarak güncellenir, kelime dağarcığınızı ve kelime kalıplarınızı öğrenir.
- **Kalıcı öğrenme:** Öğrenilen veriler NVDA kullanıcı yapılandırmanıza kaydedilir ve yeniden başlatmalarda birikir.
- **Ön eğitimli:** Yayınlanmış yazılar ve kısaltmalar da dahil olmak üzere yaygın İngilizce kelime çiftleri üzerine eğitilmiş n-gram verileriyle birlikte gönderilir.
- **Açma/kapatma:** Tahmini açmak veya kapatmak için NVDA+Alt+P tuşlarına basın.
- **Ayarlar paneli:** NVDA'nın Ayarlar iletişim kutusundan tahmin sayısını, bip sesini ve öğrenmeyi yapılandırın.
- **Yeniden eşlenebilir tuşlar:** Tüm kısayollar, NVDA'nın Giriş Hareketleri iletişim kutusundaki "Word Predictor" altında görünür.
- **Her yerde çalışır:** Küresel bir eklenti olarak tahmin, metin yazdığınız her uygulamada çalışır.
- **Terminal uyumlu:** Terminal uygulamalarındaki (Windows Terminal, PowerShell, CMD, WSL, PuTTY ve 25'ten fazla diğer) tahminleri otomatik olarak devre dışı bırakır. Ayarlardan kapatılabilir.
- **Özel uygulama hariç tutma:** Tahmin istemediğiniz yerlere kendi uygulamalarınızı (MUD istemcileri, kod düzenleyicileri, eğik çizgi komutlarıyla sohbet uygulamaları vb.) Ayarlar > Word Predictor'a ekleyin. Satır başına bir uygulama adı.
- **Noktalama işaretlerine duyarlı ekleme:** Bir nokta, soru işareti veya ünlem işaretinden sonra bir tahmini kabul ettiğinizde, otomatik olarak önüne bir boşluk eklenir ve ilk harf büyük harfle yazılır. Virgül, noktalı virgül veya iki nokta üst üsteden sonra büyük harf olmadan bir boşluk eklenir.

## Tuş Bağlamaları

| Anahtar | Eylem |
|-----|--------|
| NVDA+Kontrol+1 ila NVDA+Kontrol+0 | Tahmin 1-10'u kabul et (yalnızca tahminler etkin olduğunda müdahale eder) |
| NVDA+Alt+P | Kelime tahminini aç/kapat |
| NVDA+Alt+O | Talep üzerine tahminler isteyin (kısmi veya tam) |
| NVDA+Alt+L | Öğrenmeyi manuel olarak diske kaydedin |

Tüm tuş atamaları, NVDA'nın Girdi Hareketleri iletişim kutusunda "Kelime Tahmincisi" kategorisi altında yeniden eşlenebilir.

## Kurulum

1. En son sürüm olan `.nvda-addon` dosyasını [Releases sayfasından](https://github.com/RareBird15/wordpredictor/releases) indirin.
2. NVDA'nın eklenti yükleyicisi aracılığıyla yüklemek için dosyayı Windows Dosya Gezgini'nden açın.
3. NVDA'yı yeniden başlatın.

## Kullanım

1. Herhangi bir metin alanına yazmaya başlayın.
2. Bir kelimeden sonra Aralık tuşuna bastığınızda, kısa bir bip sesi ve ardından en fazla 5 tahmin duyacaksınız.
3. İlk tahmini kabul etmek için NVDA+Kontrol+1 tuşlarına, ikinci tahmin için NVDA+Kontrol+2 tuşlarına vb. basın.
4. Tahmin edilen kelime, sonunda bir boşluk bırakılarak otomatik olarak yazılır.
5. Kısmi kelime tahmini için kelimenin bir kısmını yazın ve NVDA+Alt+O tuşlarına basın.
6. Tahmini açmak veya kapatmak için NVDA+Alt+P tuşlarına basın.
7. Ayarları NVDA Menüsü > Ayarlar > Kelime Tahmincisi dalı altından yapılandırın.

## Nasıl Çalışır

Eklenti iki tahmin motoru kullanır:

**N-gram modeli (varsayılan):** Kneser-Ney yumuşatma ile bigram ve trigram analizini kullanır. Hızlıdır, hafiftir ve yazdıklarınızdan gerçek zamanlı olarak öğrenir. Harici bağımlılık gerekmez.

**LSTM sinir ağı (isteğe bağlı):** 6 kelimelik bir bağlam penceresine sahip, 20 milyon modern film ve TV diyaloğu (OpenSubtitles) ile eğitilmiş küçük bir dil modeli. Doğal konuşma kalıplarını anlayan bağlama duyarlı tahminler sağlar. Ayarlar > Kelime Tahmincisi'nde geçiş yapın. Onnxruntime gerektirir (paketlenmiş DLL'ler dahildir veya 'pip install onnxruntime' yoluyla yüklenir).

Her iki motor da birlikte çalışır; LSTM önce bağlama duyarlı öneriler sunar, ardından n-gram modeli kalan boşlukları kendi yazınızdan öğrenilen kelimelerle doldurur.

### N-gram Model Detayları

- **Bigramlar:** Genellikle hangi kelimelerin diğer kelimelerden sonra geldiğini izler (ör. "the" -> "system")
- **Trigramlar:** Genellikle iki kelimelik kombinasyonlardan sonra gelen kelimeleri izler (ör. "Ben" -> "değilim")
- **Kneser-Ney yumuşatma:** Tahminleri ham frekansa göre sıralamak yerine enterpolasyonlu Kneser-Ney olasılığını kullanır. Bu, sık sık ancak yalnızca belirli ifadelerde ("Yeni"den sonra "York" gibi) görünen kelimeler yerine birçok farklı bağlamda görünen kelimeleri ("the", "is", "and" gibi) ödüllendirir. Ayarlanmış olasılıklarla daha düşük dereceli n-gramlara geri dönerek, görünmeyen n-gramları incelikli bir şekilde işler.
- **Üç düzeyli enterpolasyon:** Trigram olasılığı, unigram devam olasılığıyla harmanlanan bigram olasılığıyla harmanlanır. Bu, tam bağlamda hiç görülmeyen kelimelerin bile devam olarak ne kadar yaygın olduklarına bağlı olarak bir olasılık elde ettiği anlamına gelir.
- **Kısmi eşleştirme:** Bir kelimenin bir kısmını yazdığınızda, eklenti tüm n gramlarda yazdıklarınızla başlayan kelimeleri arar ve bunları KN olasılığına göre sıralar
- **Gerçek zamanlı öğrenme:** Yazdığınız her kelime, n-gram sayısını ve türetilmiş istatistikleri günceller, böylece model, yazma stilinize uyum sağlar
- **Kalıcı depolama:** Öğrenme, NVDA kullanıcı yapılandırma dizininizdeki `wordPredictor_learned.json` dosyasına kaydedilir
- **Geriye dönük uyumlu:** v1.1.0'dan alınan mevcut öğrenilen veriler geçiş olmadan yüklenir. Orijinal frekansa dayalı davranışı geri yüklemek için ayarlardan yumuşatma kapatılabilir.

N-gram verileri bir JSON dosyası olarak saklanır ve başlangıçta yüklenir. Harici Python bağımlılığına gerek yoktur.

## Teknik Detaylar

- **NVDA sürümü:** NVDA 2026.1 veya üzerini gerektirir (Python 3.13, 64 bit)
- **Mimarlık:** Giriş takibi için `event_typedCharacter' kullanan genel eklenti
- **Tahmin motoru:** Özel n-gram uygulaması, çalışma zamanında NLTK bağımlılığı yok
- **Veri dosyası:** Bigram ve trigram sayımlarını içeren ~1,6 MB JSON dosyası
- **Yapılandırma:** NVDA'nın yapılandırmasında 'wordPredictor' tuşu altında saklanan ayarlar

## Değişiklik günlüğü

Tam sürüm geçmişi için [CHANGELOG.md](CHANGELOG.md) adresine bakın.

## Lisans

GPL v2, NVDA ile aynı.

## Yazar

Lanie Carmelo-Molinar - [lanie.work](https://lanie.work)

Bunu, mevcut kelime tahmin araçlarının ekran okuyucularla çalışmaması nedeniyle geliştiren kör bir NVDA kullanıcısı.
