# Device Data MCP Server

Yerel `mcp_demo` PostgreSQL ölçüm ve olay verisini salt okunur MCP araçları, kaynakları ve promptlarıyla sunan Python server.

## Araçlar

| Tool | İşlev |
| --- | --- |
| `list_devices` | Cihazları ve beklenen ölçüm aralığını listeler |
| `get_data_range` | Ölçüm sayısını ve UTC veri aralığını döndürür |
| `get_measurement_summary` | Cihaz bazında sayım, min, max ve ortalama üretir |
| `find_data_gaps` | Beklenen örnekleme aralığına göre eksikleri bulur |
| `find_threshold_violations` | Akım ve sıcaklık demo eşiklerini kontrol eder |
| `find_duplicate_measurements` | Tekrarlanan cihaz-zaman gruplarını bulur |
| `get_latest_measurements` | En yeni ölçümleri listeler |
| `get_daily_summary` | Günlük istatistikleri cihaz bazında üretir |
| `get_hourly_profile` | Günün saatlerine göre ortalama profili çıkarır |
| `compare_devices` | Bütün cihazların ortalama ve standart sapmalarını karşılaştırır |
| `get_measurement_percentiles` | Yüzde 50, 90, 95 ve 99 ölçüm değerlerini hesaplar |
| `get_correlation_analysis` | Akım, gerilim ve sıcaklık korelasyonlarını hesaplar |
| `get_time_bucket_summary` | Ölçümleri seçilen dakika dilimlerinde özetler |
| `get_device_health_report` | Eksik, tekrarlı ve eşik dışı verilere göre sağlık raporu üretir |
| `list_device_events` | Cihaz olaylarını dönem ve cihaz filtresiyle listeler |
| `get_device_event_summary` | Olayları cihaz, lokasyon, tür ve UTC saate göre özetler |
| `generate_device_event_report` | Seçilen dönem için modern panel tasarımlı PDF olay raporu üretir |

Server genel SQL çalıştırma aracı sunmaz ve PostgreSQL'e `mcp_demo_mcp_reader` rolüyle bağlanır. Bu rol yalnızca `devices`, `measurements` ve `device_events` tablolarını okuyabilir. PDF dosyaları `output/pdf` altında oluşturulur; bu işlem veritabanına yazmaz.

## MCP kaynakları ve prompt

| Tür | Adres veya ad | İşlev |
| --- | --- | --- |
| Resource | `device-events://catalog` | Bütün olayların genel özetini JSON olarak sunar |
| Resource template | `device-events://device/{device_id}` | Tek cihazın özetini ve son olaylarını JSON olarak sunar |
| Prompt | `cihaz_olay_raporu` | Dönem ve isteğe bağlı cihaz için analiz ve PDF üretim akışını tarif eder |

## Yerel çalıştırma

Gereksinimler:

- Docker Desktop çalışıyor olmalı.
- `mcp-demo-lab-db-1` sağlıklı olmalı.
- `C:\Users\<kullanıcı>\Downloads\mcp_docker\.env` mevcut olmalı.
- Sanal ortamda `requirements.txt` bağımlılıkları kurulmuş olmalı.

Server'ı stdio modunda başlatmak için:

```powershell
.\run_server.ps1
```

Bu komut normal terminalde çalıştırıldığında çıktı bekliyormuş gibi görünür; stdio MCP server istemciden protokol mesajı bekler. Codex veya Claude Code daha sonra aynı komutu alt süreç olarak başlatacak.

Testleri çalıştırmak için:

```powershell
.\test.ps1
```

Demo veri seti 5 cihaz ve 35.945 sentetik ölçüm içerir. İlk kurulumdaki 7.145 ölçümü güvenli ve tekrar çalıştırılabilir biçimde genişletmek için:

```powershell
.\expand_demo_data.ps1
```

Script yalnızca `mcp_demo` veritabanında çalışır, 6-9 Kasım 2026 verilerini ekler ve daha önce eklenen satırları çoğaltmaz.

Lokasyon alanını, `device_events` tablosunu ve 70 sentetik olay kaydını eklemek için:

```powershell
.\migrate_device_events.ps1
```

Geçiş yalnızca `mcp_demo` üzerinde çalışır ve tekrar çalıştırıldığında olayları çoğaltmaz. Geri alma SQL'i `rollback_device_events.sql` dosyasında tutulur; çalıştırılması `device_events` verisini ve `location` alanını siler, bu yüzden otomatik uygulanmaz.

PDF rapor örneği için MCP istemcisinden şu isteği kullanın:

```text
6-11 Kasım 2026 UTC dönemi için bütün cihazların olay PDF raporunu oluştur.
```

Tek cihaz raporunda aynı döneme `device_id` eklenir. Cihaz belirtilmezse rapor cihaz, lokasyon, olay türü ve UTC saat yoğunluklarını karşılaştırır.
Rapor; KPI kartları, önem dağılımı, saat ısı haritası, cihaz karşılaştırması ve renk kodlu olay durumları içerir.

Farklı Docker ortam dosyası kullanılacaksa yolu parola değerini göstermeden ayarlayın:

```powershell
$env:MCP_DB_ENV_FILE = 'C:\path\to\.env'
.\run_server.ps1
```

## Güvenlik sınırı

- Parola kaynak kodunda veya README içinde tutulmaz.
- Reader parolası mevcut Docker sırrından tek yönlü türetilir ve diske yazılmaz.
- Her bağlantı PostgreSQL `default_transaction_read_only=on` ayarıyla açılır.
- Tool'lar yalnızca sabit ve parametreli sorgular çalıştırır.
- PDF tool'u yalnızca proje içindeki `output/pdf` dizinine yazar.
- Bu veri sentetik demo verisidir; şirket verisi bağlanmadan önce yetki ve veri paylaşımı ayrıca incelenmelidir.

## İstemci bağlantıları

Aynı `run_server.ps1` başlatıcısı aşağıdaki global istemci kayıtlarına `device-data` adıyla eklenmiştir:

- ChatGPT masaüstü ve Codex: `%USERPROFILE%\.codex\config.toml`
- Claude Code yerel oturumları: `%USERPROFILE%\.claude.json`
- Claude Desktop klasik kurulum: `%APPDATA%\Claude\claude_desktop_config.json`
- Claude Desktop Microsoft Store/MSIX (bu bilgisayar): `%LOCALAPPDATA%\Claude-Data\claude_pzs8sxrjxfjjc\claude_desktop_config.json`
- Antigravity IDE: `%USERPROFILE%\.gemini\config\mcp_config.json`

İstemci açıksa yeni MCP kaydını yüklemek için uygulamayı yeniden başlatın. Server sürekli arka planda tutulmaz; istemci gerektiğinde stdio alt süreci olarak başlatır.

Claude Desktop'ta `Ayarlar > Geliştirici > Yapılandırmayı düzenle` düğmesi her zaman uygulamanın gerçekten okuduğu dosyayı açar. Store/MSIX sürümünde bu yol klasik `%APPDATA%` yolundan farklı olabilir.

## Yeni tool eklemek

Yeni fonksiyonlar `server.py` içinde `@mcp.tool()` dekoratörüyle tanımlanır. Fonksiyon adı MCP tool adı, docstring ise modelin gördüğü Türkçe açıklamadır. Parametrelerin type hint'leri MCP giriş şemasını oluşturur.

Örnek:

```python
@mcp.tool()
def get_device_measurement_count(device_id: int) -> dict[str, Any]:
    """Bir cihazın toplam ölçüm sayısını döndürür."""
    if device_id < 1:
        raise ToolError("device_id pozitif bir tam sayı olmalıdır.")

    return _fetch_one(
        """
        SELECT device_id, count(*)::bigint AS measurement_count
        FROM public.measurements
        WHERE device_id = %s
        GROUP BY device_id
        """,
        (device_id,),
    )
```

Yeni tool ekleme sırası:

1. Fonksiyonu `server.py` içinde `if __name__ == "__main__"` bölümünden önce tanımlayın.
2. `@mcp.tool()` dekoratörünü ve anlaşılır Türkçe docstring'i ekleyin.
3. Dışarıdan gelen değerleri doğrulayın ve SQL parametrelerini `%s` ile geçirin.
4. Tool adını `tests/test_server.py` içindeki beklenen tool listesine ekleyin.
5. Sonucu kontrol eden küçük bir test yazıp `.\test.ps1` çalıştırın.
6. Açık istemcide MCP bağlantısını yenileyin veya istemciyi yeniden başlatın.

Resource eklemek için `@mcp.resource("scheme://adres")`, resource template için URI içinde `{parametre}`, prompt eklemek için `@mcp.prompt()` dekoratörü kullanılır. Prompt bir tool'u kendisi çalıştırmaz; modele tekrar kullanılabilir bir çalışma talimatı verir.

Aynı `run_server.ps1` bütün istemciler tarafından kullanıldığı için tool'u Codex, Claude ve Antigravity'ye ayrı ayrı yeniden eklemek gerekmez. Genel SQL çalıştıran veya yazma yapan bir tool eklemeden önce PostgreSQL rol yetkilerini ayrıca tasarlayın; mevcut rol salt okunurdur.
