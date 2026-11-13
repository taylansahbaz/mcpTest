BEGIN;

DO $$
BEGIN
    IF current_database() <> 'mcp_demo' THEN
        RAISE EXCEPTION 'Yanlış veritabanı. Yalnızca mcp_demo üzerinde çalıştırın.';
    END IF;
END $$;

-- 6-9 Kasım 2026 UTC: beş cihaz için dakikada bir deterministik sentetik ölçüm.
-- NOT EXISTS denetimi dosyanın tekrar çalıştırılmasını güvenli hale getirir.
INSERT INTO public.measurements (device_id, readtime, current, voltage, temperature)
SELECT d.id,
       timestamptz '2026-11-06 00:00:00+00' + g.minute_no * interval '1 minute',
       round((6.0 + d.id * 0.25 + sin((g.minute_no + d.id * 7) / 20.0) * 0.4)::numeric, 3),
       round((230.0 + sin((g.minute_no + d.id * 11) / 30.0) * 2.0)::numeric, 3),
       round((35.0 + d.id + sin((g.minute_no + d.id * 13) / 40.0) * 1.5)::numeric, 3)
FROM public.devices d
CROSS JOIN generate_series(0, 5759) AS g(minute_no)
WHERE NOT EXISTS (
    SELECT 1
    FROM public.measurements existing
    WHERE existing.device_id = d.id
      AND existing.readtime = timestamptz '2026-11-06 00:00:00+00'
                              + g.minute_no * interval '1 minute'
)
ORDER BY d.id, g.minute_no;

DO $$
BEGIN
    IF (SELECT count(*) FROM public.devices) <> 5 THEN
        RAISE EXCEPTION 'Cihaz sayısı beklenen 5 değil.';
    END IF;
    IF (SELECT count(*) FROM public.measurements) <> 35945 THEN
        RAISE EXCEPTION 'Ölçüm sayısı beklenen 35945 değil.';
    END IF;
END $$;

COMMIT;
