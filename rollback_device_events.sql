BEGIN;

DO $$
BEGIN
    IF current_database() <> 'mcp_demo' THEN
        RAISE EXCEPTION 'Yanlış veritabanı. Yalnızca mcp_demo üzerinde çalıştırın.';
    END IF;
END $$;

DROP TABLE IF EXISTS public.device_events;
ALTER TABLE public.devices DROP COLUMN IF EXISTS location;

COMMIT;
