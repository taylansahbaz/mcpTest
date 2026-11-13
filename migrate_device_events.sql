BEGIN;

DO $$
BEGIN
    IF current_database() <> 'mcp_demo' THEN
        RAISE EXCEPTION 'Yanlış veritabanı. Yalnızca mcp_demo üzerinde çalıştırın.';
    END IF;
END $$;

ALTER TABLE public.devices
    ADD COLUMN IF NOT EXISTS location text;

UPDATE public.devices
SET location = CASE id
    WHEN 1 THEN 'İstanbul'
    WHEN 2 THEN 'İstanbul'
    WHEN 3 THEN 'Ankara'
    WHEN 4 THEN 'İzmir'
    WHEN 5 THEN 'Ankara'
    ELSE 'Bilinmiyor'
END
WHERE location IS NULL;

ALTER TABLE public.devices
    ALTER COLUMN location SET DEFAULT 'Bilinmiyor',
    ALTER COLUMN location SET NOT NULL;

CREATE TABLE IF NOT EXISTS public.device_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id integer NOT NULL REFERENCES public.devices(id) ON DELETE RESTRICT,
    event_time timestamp with time zone NOT NULL,
    event_type text NOT NULL CHECK (
        event_type IN (
            'data_gap',
            'high_current',
            'high_temperature',
            'voltage_fluctuation',
            'connection_loss',
            'maintenance'
        )
    ),
    severity text NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    title text NOT NULL,
    description text NOT NULL,
    resolved_at timestamp with time zone,
    source text NOT NULL DEFAULT 'sentetik_demo',
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT device_events_resolved_after_event
        CHECK (resolved_at IS NULL OR resolved_at >= event_time),
    CONSTRAINT device_events_unique_demo_event
        UNIQUE (device_id, event_time, event_type)
);

CREATE INDEX IF NOT EXISTS device_events_event_time_idx
    ON public.device_events (event_time);
CREATE INDEX IF NOT EXISTS device_events_device_time_idx
    ON public.device_events (device_id, event_time);
CREATE INDEX IF NOT EXISTS device_events_severity_idx
    ON public.device_events (severity);

WITH event_plan(device_id, event_count) AS (
    VALUES (1, 8), (2, 12), (3, 24), (4, 10), (5, 16)
), generated AS (
    SELECT p.device_id,
           n.event_no,
           timestamptz '2026-11-06 00:00:00+00'
               + ((n.event_no - 1) % 5) * interval '1 day'
               + CASE (n.event_no + p.device_id) % 6
                   WHEN 0 THEN interval '08 hours'
                   WHEN 1 THEN interval '10 hours'
                   WHEN 2 THEN interval '14 hours'
                   WHEN 3 THEN interval '18 hours'
                   WHEN 4 THEN interval '21 hours'
                   ELSE interval '23 hours'
                 END
               + ((n.event_no * 7 + p.device_id * 3) % 60) * interval '1 minute'
               AS event_time,
           CASE (n.event_no + p.device_id) % 6
               WHEN 0 THEN 'high_temperature'
               WHEN 1 THEN 'high_current'
               WHEN 2 THEN 'connection_loss'
               WHEN 3 THEN 'voltage_fluctuation'
               WHEN 4 THEN 'data_gap'
               ELSE 'maintenance'
           END AS event_type
    FROM event_plan p
    CROSS JOIN LATERAL generate_series(1, p.event_count) AS n(event_no)
), classified AS (
    SELECT *,
           CASE
               WHEN event_type IN ('high_temperature', 'connection_loss')
                    AND event_no % 4 = 0 THEN 'critical'
               WHEN event_type = 'maintenance' THEN 'info'
               ELSE 'warning'
           END AS severity
    FROM generated
)
INSERT INTO public.device_events (
    device_id,
    event_time,
    event_type,
    severity,
    title,
    description,
    resolved_at,
    source
)
SELECT device_id,
       event_time,
       event_type,
       severity,
       CASE event_type
           WHEN 'high_temperature' THEN 'Yüksek sıcaklık algılandı'
           WHEN 'high_current' THEN 'Akım eşiği aşıldı'
           WHEN 'connection_loss' THEN 'Cihaz bağlantısı kesildi'
           WHEN 'voltage_fluctuation' THEN 'Gerilim dalgalanması oluştu'
           WHEN 'data_gap' THEN 'Ölçüm verisi kesintiye uğradı'
           ELSE 'Planlı bakım kaydı'
       END,
       CASE event_type
           WHEN 'high_temperature' THEN 'Sıcaklık değeri demo alarm sınırının üzerine çıktı.'
           WHEN 'high_current' THEN 'Akım değeri beklenen çalışma aralığının üzerine çıktı.'
           WHEN 'connection_loss' THEN 'Cihazdan geçici olarak telemetri alınamadı.'
           WHEN 'voltage_fluctuation' THEN 'Gerilim değerinde kısa süreli dalgalanma gözlendi.'
           WHEN 'data_gap' THEN 'Beklenen örnekleme aralığında ölçüm kaydı bulunamadı.'
           ELSE 'Cihaz için planlı kontrol ve bakım işlemi kaydedildi.'
       END,
       CASE
           WHEN event_no % 7 = 0 THEN NULL
           ELSE event_time + ((event_no % 5) + 1) * interval '12 minutes'
       END,
       'sentetik_demo'
FROM classified
ON CONFLICT (device_id, event_time, event_type) DO NOTHING;

DO $$
DECLARE
    event_total bigint;
BEGIN
    IF (SELECT count(*) FROM public.devices WHERE location IS NULL) <> 0 THEN
        RAISE EXCEPTION 'Lokasyonu eksik cihaz bulundu.';
    END IF;

    SELECT count(*) INTO event_total
    FROM public.device_events
    WHERE source = 'sentetik_demo';

    IF event_total <> 70 THEN
        RAISE EXCEPTION 'Sentetik olay sayısı beklenen 70 değil: %', event_total;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mcp_demo_mcp_reader') THEN
        GRANT SELECT ON TABLE public.device_events TO mcp_demo_mcp_reader;
    END IF;
END $$;

COMMIT;
