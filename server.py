from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from psycopg.rows import dict_row

from reporting import create_device_event_report


mcp = MCPServer(
    "device-data",
    instructions=(
        "Sentetik mcp_demo cihaz ölçümlerine ve olaylarına salt okunur erişim sağlar. "
        "Önce özet ve anomali araçlarını kullan; zaman damgaları UTC döner. "
        "Cihaz olay raporu için cihaz_olay_raporu promptunu ve "
        "generate_device_event_report aracını kullan."
    ),
)

PROJECT_ROOT = Path(__file__).resolve().parent
REPORT_OUTPUT_DIR = PROJECT_ROOT / "output" / "pdf"


def _connect() -> psycopg.Connection[dict[str, Any]]:
    password = os.environ.get("PGPASSWORD")
    if not password:
        raise ToolError("Veritabanı bilgileri eksik. Sunucuyu run_server.ps1 ile başlatın.")

    try:
        return psycopg.connect(
            host=os.environ.get("PGHOST", "127.0.0.1"),
            port=int(os.environ.get("PGPORT", "55432")),
            dbname=os.environ.get("PGDATABASE", "mcp_demo"),
            user=os.environ.get("PGUSER", "mcp_demo_mcp_reader"),
            password=password,
            connect_timeout=5,
            options="-c default_transaction_read_only=on -c timezone=UTC",
            application_name="device-data-mcp",
            row_factory=dict_row,
        )
    except (ValueError, psycopg.Error) as exc:
        raise ToolError("mcp_demo veritabanı bağlantısı kurulamadı.") from exc


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    try:
        with _connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return [
                    {key: _json_value(value) for key, value in row.items()}
                    for row in cursor.fetchall()
                ]
    except ToolError:
        raise
    except psycopg.Error as exc:
        raise ToolError("Veritabanı sorgusu çalıştırılamadı.") from exc


def _fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    rows = _fetch_all(query, params)
    if not rows:
        raise ToolError("Sorgu sonuç döndürmedi.")
    return rows[0]


def _parse_timestamp(value: str | None, parameter_name: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ToolError(f"{parameter_name}, saat dilimi içeren ISO 8601 biçiminde olmalıdır.") from exc
    if parsed.tzinfo is None:
        raise ToolError(f"{parameter_name} saat dilimi içermelidir; örneğin +00:00 veya Z.")
    return parsed.astimezone(timezone.utc)


def _measurement_filter(
    alias: str,
    device_id: int | None,
    start_time: str | None,
    end_time: str | None,
) -> tuple[str, tuple[Any, ...]]:
    if device_id is not None and device_id < 1:
        raise ToolError("device_id pozitif bir tam sayı olmalıdır.")

    start = _parse_timestamp(start_time, "start_time")
    end = _parse_timestamp(end_time, "end_time")
    if start is not None and end is not None and start >= end:
        raise ToolError("start_time, end_time değerinden önce olmalıdır.")

    clauses: list[str] = []
    params: list[Any] = []
    if device_id is not None:
        clauses.append(f"{alias}.device_id = %s")
        params.append(device_id)
    if start is not None:
        clauses.append(f"{alias}.readtime >= %s")
        params.append(start)
    if end is not None:
        clauses.append(f"{alias}.readtime < %s")
        params.append(end)

    return (" AND ".join(clauses) if clauses else "TRUE", tuple(params))


def _event_filter(
    alias: str,
    device_id: int | None,
    start_time: str | None,
    end_time: str | None,
) -> tuple[str, tuple[Any, ...]]:
    if device_id is not None and device_id < 1:
        raise ToolError("device_id pozitif bir tam sayı olmalıdır.")

    start = _parse_timestamp(start_time, "start_time")
    end = _parse_timestamp(end_time, "end_time")
    if start is not None and end is not None and start >= end:
        raise ToolError("start_time, end_time değerinden önce olmalıdır.")

    clauses: list[str] = []
    params: list[Any] = []
    if device_id is not None:
        clauses.append(f"{alias}.device_id = %s")
        params.append(device_id)
    if start is not None:
        clauses.append(f"{alias}.event_time >= %s")
        params.append(start)
    if end is not None:
        clauses.append(f"{alias}.event_time < %s")
        params.append(end)

    return (" AND ".join(clauses) if clauses else "TRUE", tuple(params))


def _validated_limit(limit: int) -> int:
    if not 1 <= limit <= 100:
        raise ToolError("limit 1 ile 100 arasında olmalıdır.")
    return limit


@mcp.tool()
def list_devices() -> dict[str, Any]:
    """Cihazları ve beklenen ölçüm aralıklarını listeler."""
    devices = _fetch_all(
        """
        SELECT id, name, location, expected_interval_seconds
        FROM public.devices
        ORDER BY id
        """
    )
    return {"device_count": len(devices), "devices": devices}


@mcp.tool()
def get_data_range(device_id: int | None = None) -> dict[str, Any]:
    """Ölçüm sayısını ve UTC veri aralığını, isteğe bağlı olarak tek cihaz için döndürür."""
    where_clause, params = _measurement_filter("m", device_id, None, None)
    return _fetch_one(
        f"""
        SELECT count(*)::bigint AS measurement_count,
               count(DISTINCT device_id)::integer AS device_count,
               min(readtime) AS data_start,
               max(readtime) AS data_end
        FROM public.measurements m
        WHERE {where_clause}
        """,
        params,
    )


@mcp.tool()
def get_measurement_summary(
    device_id: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    """UTC zaman aralındaki ölçüm sayılarını ve istatistikleri cihaz bazında özetler."""
    where_clause, params = _measurement_filter("m", device_id, start_time, end_time)
    summaries = _fetch_all(
        f"""
        SELECT d.id AS device_id,
               d.name AS device_name,
               count(m.id)::bigint AS measurement_count,
               count(DISTINCT m.readtime)::bigint AS distinct_timestamps,
               min(m.readtime) AS data_start,
               max(m.readtime) AS data_end,
               round(avg(m.current), 3) AS average_current,
               min(m.current) AS minimum_current,
               max(m.current) AS maximum_current,
               round(avg(m.voltage), 3) AS average_voltage,
               min(m.voltage) AS minimum_voltage,
               max(m.voltage) AS maximum_voltage,
               round(avg(m.temperature), 3) AS average_temperature,
               min(m.temperature) AS minimum_temperature,
               max(m.temperature) AS maximum_temperature
        FROM public.measurements m
        JOIN public.devices d ON d.id = m.device_id
        WHERE {where_clause}
        GROUP BY d.id, d.name
        ORDER BY d.id
        """,
        params,
    )
    return {"device_count": len(summaries), "summaries": summaries}


@mcp.tool()
def find_data_gaps(
    device_id: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    """Her cihazın beklenen örnekleme aralığına göre eksik ölçüm aralıklarını bulur."""
    where_clause, params = _measurement_filter("m", device_id, start_time, end_time)
    gaps = _fetch_all(
        f"""
        WITH unique_times AS (
            SELECT DISTINCT m.device_id, m.readtime
            FROM public.measurements m
            WHERE {where_clause}
        ), sequenced AS (
            SELECT device_id,
                   lag(readtime) OVER (PARTITION BY device_id ORDER BY readtime) AS previous_time,
                   readtime AS next_time
            FROM unique_times
        )
        SELECT d.id AS device_id,
               d.name AS device_name,
               s.previous_time,
               s.next_time,
               (
                   extract(epoch FROM (s.next_time - s.previous_time))
                   / d.expected_interval_seconds
               )::integer - 1 AS missing_samples
        FROM sequenced s
        JOIN public.devices d ON d.id = s.device_id
        WHERE s.previous_time IS NOT NULL
          AND s.next_time - s.previous_time
              > d.expected_interval_seconds * interval '1 second'
        ORDER BY d.id, s.previous_time
        """,
        params,
    )
    return {
        "gap_count": len(gaps),
        "missing_sample_count": sum(row["missing_samples"] for row in gaps),
        "gaps": gaps,
    }


@mcp.tool()
def find_threshold_violations(
    current_threshold: float = 12.0,
    temperature_threshold: float = 70.0,
    device_id: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Verilen demo eşiklerinin üzerindeki akım veya sıcaklık ölçümlerini bulur."""
    if current_threshold < 0 or temperature_threshold < 0:
        raise ToolError("Eşik değerleri sıfır veya daha büyük olmalıdır.")
    limit = _validated_limit(limit)
    where_clause, filter_params = _measurement_filter("m", device_id, start_time, end_time)

    summaries = _fetch_all(
        f"""
        SELECT d.id AS device_id,
               d.name AS device_name,
               count(*) FILTER (WHERE m.current > %s)::bigint AS current_violations,
               count(*) FILTER (WHERE m.temperature > %s)::bigint AS temperature_violations
        FROM public.measurements m
        JOIN public.devices d ON d.id = m.device_id
        WHERE {where_clause}
        GROUP BY d.id, d.name
        HAVING count(*) FILTER (WHERE m.current > %s) > 0
            OR count(*) FILTER (WHERE m.temperature > %s) > 0
        ORDER BY d.id
        """,
        (
            current_threshold,
            temperature_threshold,
            *filter_params,
            current_threshold,
            temperature_threshold,
        ),
    )

    samples = _fetch_all(
        f"""
        SELECT d.id AS device_id,
               d.name AS device_name,
               m.readtime,
               m.current,
               m.voltage,
               m.temperature,
               (m.current > %s) AS current_violation,
               (m.temperature > %s) AS temperature_violation
        FROM public.measurements m
        JOIN public.devices d ON d.id = m.device_id
        WHERE {where_clause}
          AND (m.current > %s OR m.temperature > %s)
        ORDER BY m.readtime, d.id
        LIMIT %s
        """,
        (
            current_threshold,
            temperature_threshold,
            *filter_params,
            current_threshold,
            temperature_threshold,
            limit + 1,
        ),
    )
    samples_truncated = len(samples) > limit
    samples = samples[:limit]

    return {
        "current_threshold": current_threshold,
        "temperature_threshold": temperature_threshold,
        "current_violation_count": sum(row["current_violations"] for row in summaries),
        "temperature_violation_count": sum(row["temperature_violations"] for row in summaries),
        "summaries": summaries,
        "samples": samples,
        "samples_truncated": samples_truncated,
    }


@mcp.tool()
def find_duplicate_measurements(
    device_id: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Birden fazla ölçüm satırı bulunan cihaz-zaman damgası gruplarını bulur."""
    limit = _validated_limit(limit)
    where_clause, filter_params = _measurement_filter("m", device_id, start_time, end_time)
    duplicates = _fetch_all(
        f"""
        SELECT d.id AS device_id,
               d.name AS device_name,
               m.readtime,
               count(*)::integer AS row_count
        FROM public.measurements m
        JOIN public.devices d ON d.id = m.device_id
        WHERE {where_clause}
        GROUP BY d.id, d.name, m.readtime
        HAVING count(*) > 1
        ORDER BY d.id, m.readtime
        LIMIT %s
        """,
        (*filter_params, limit + 1),
    )
    results_truncated = len(duplicates) > limit
    duplicates = duplicates[:limit]
    return {
        "duplicate_group_count": len(duplicates),
        "duplicates": duplicates,
        "results_truncated": results_truncated,
    }


@mcp.tool()
def get_latest_measurements(
    device_id: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """En yeni ölçümleri, isteğe bağlı olarak tek cihaz için listeler."""
    limit = _validated_limit(limit)
    where_clause, params = _measurement_filter("m", device_id, None, None)
    measurements = _fetch_all(
        f"""
        SELECT m.id,
               d.id AS device_id,
               d.name AS device_name,
               m.readtime,
               m.current,
               m.voltage,
               m.temperature
        FROM public.measurements m
        JOIN public.devices d ON d.id = m.device_id
        WHERE {where_clause}
        ORDER BY m.readtime DESC, m.id DESC
        LIMIT %s
        """,
        (*params, limit),
    )
    return {"measurement_count": len(measurements), "measurements": measurements}


@mcp.tool()
def get_daily_summary(
    device_id: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    """Günlük ölçüm sayılarını, ortalamaları ve en düşük-en yüksek değerleri özetler."""
    where_clause, params = _measurement_filter("m", device_id, start_time, end_time)
    rows = _fetch_all(
        f"""
        SELECT d.id AS device_id,
               d.name AS device_name,
               date_trunc('day', m.readtime) AS day,
               count(*)::bigint AS measurement_count,
               round(avg(m.current), 3) AS average_current,
               min(m.current) AS minimum_current,
               max(m.current) AS maximum_current,
               round(avg(m.voltage), 3) AS average_voltage,
               min(m.voltage) AS minimum_voltage,
               max(m.voltage) AS maximum_voltage,
               round(avg(m.temperature), 3) AS average_temperature,
               min(m.temperature) AS minimum_temperature,
               max(m.temperature) AS maximum_temperature
        FROM public.measurements m
        JOIN public.devices d ON d.id = m.device_id
        WHERE {where_clause}
        GROUP BY d.id, d.name, date_trunc('day', m.readtime)
        ORDER BY day, d.id
        """,
        params,
    )
    return {"summary_count": len(rows), "daily_summaries": rows}


@mcp.tool()
def get_hourly_profile(
    device_id: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    """Günün saatlerine göre ortalama akım, gerilim ve sıcaklık profilini çıkarır."""
    where_clause, params = _measurement_filter("m", device_id, start_time, end_time)
    rows = _fetch_all(
        f"""
        SELECT d.id AS device_id,
               d.name AS device_name,
               extract(hour FROM m.readtime)::integer AS hour_utc,
               count(*)::bigint AS measurement_count,
               round(avg(m.current), 3) AS average_current,
               round(avg(m.voltage), 3) AS average_voltage,
               round(avg(m.temperature), 3) AS average_temperature
        FROM public.measurements m
        JOIN public.devices d ON d.id = m.device_id
        WHERE {where_clause}
        GROUP BY d.id, d.name, extract(hour FROM m.readtime)
        ORDER BY d.id, hour_utc
        """,
        params,
    )
    return {"profile_count": len(rows), "hourly_profiles": rows}


@mcp.tool()
def compare_devices(
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    """Seçilen UTC zaman aralığında bütün cihazların temel istatistiklerini karşılaştırır."""
    where_clause, params = _measurement_filter("m", None, start_time, end_time)
    rows = _fetch_all(
        f"""
        SELECT d.id AS device_id,
               d.name AS device_name,
               count(*)::bigint AS measurement_count,
               round(avg(m.current), 3) AS average_current,
               round(stddev_pop(m.current), 3) AS current_stddev,
               round(avg(m.voltage), 3) AS average_voltage,
               round(stddev_pop(m.voltage), 3) AS voltage_stddev,
               round(avg(m.temperature), 3) AS average_temperature,
               round(stddev_pop(m.temperature), 3) AS temperature_stddev
        FROM public.measurements m
        JOIN public.devices d ON d.id = m.device_id
        WHERE {where_clause}
        GROUP BY d.id, d.name
        ORDER BY d.id
        """,
        params,
    )
    return {"device_count": len(rows), "comparisons": rows}


@mcp.tool()
def get_measurement_percentiles(
    device_id: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    """Akım, gerilim ve sıcaklık için yüzde 50, 90, 95 ve 99 değerlerini hesaplar."""
    where_clause, params = _measurement_filter("m", device_id, start_time, end_time)
    return _fetch_one(
        f"""
        SELECT count(*)::bigint AS measurement_count,
               round(percentile_cont(0.50) WITHIN GROUP (ORDER BY current)::numeric, 3) AS current_p50,
               round(percentile_cont(0.90) WITHIN GROUP (ORDER BY current)::numeric, 3) AS current_p90,
               round(percentile_cont(0.95) WITHIN GROUP (ORDER BY current)::numeric, 3) AS current_p95,
               round(percentile_cont(0.99) WITHIN GROUP (ORDER BY current)::numeric, 3) AS current_p99,
               round(percentile_cont(0.50) WITHIN GROUP (ORDER BY voltage)::numeric, 3) AS voltage_p50,
               round(percentile_cont(0.95) WITHIN GROUP (ORDER BY voltage)::numeric, 3) AS voltage_p95,
               round(percentile_cont(0.50) WITHIN GROUP (ORDER BY temperature)::numeric, 3) AS temperature_p50,
               round(percentile_cont(0.95) WITHIN GROUP (ORDER BY temperature)::numeric, 3) AS temperature_p95
        FROM public.measurements m
        WHERE {where_clause}
        """,
        params,
    )


@mcp.tool()
def get_correlation_analysis(
    device_id: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    """Akım, gerilim ve sıcaklık çiftleri arasındaki Pearson korelasyonlarını hesaplar."""
    where_clause, params = _measurement_filter("m", device_id, start_time, end_time)
    return _fetch_one(
        f"""
        SELECT count(*)::bigint AS measurement_count,
               round(corr(current::double precision, voltage::double precision)::numeric, 4)
                   AS current_voltage_correlation,
               round(corr(current::double precision, temperature::double precision)::numeric, 4)
                   AS current_temperature_correlation,
               round(corr(voltage::double precision, temperature::double precision)::numeric, 4)
                   AS voltage_temperature_correlation
        FROM public.measurements m
        WHERE {where_clause}
        """,
        params,
    )


@mcp.tool()
def get_time_bucket_summary(
    bucket_minutes: int = 60,
    device_id: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    """Ölçümleri 5, 15, 30, 60, 360 veya 1440 dakikalık zaman dilimlerinde özetler."""
    allowed_buckets = {5, 15, 30, 60, 360, 1440}
    if bucket_minutes not in allowed_buckets:
        raise ToolError("bucket_minutes şu değerlerden biri olmalıdır: 5, 15, 30, 60, 360, 1440.")
    where_clause, params = _measurement_filter("m", device_id, start_time, end_time)
    rows = _fetch_all(
        f"""
        SELECT d.id AS device_id,
               d.name AS device_name,
               date_bin(make_interval(mins => %s), m.readtime, timestamptz '2000-01-01 00:00:00+00')
                   AS bucket_start,
               count(*)::bigint AS measurement_count,
               round(avg(m.current), 3) AS average_current,
               round(avg(m.voltage), 3) AS average_voltage,
               round(avg(m.temperature), 3) AS average_temperature
        FROM public.measurements m
        JOIN public.devices d ON d.id = m.device_id
        WHERE {where_clause}
        GROUP BY d.id, d.name, bucket_start
        ORDER BY bucket_start, d.id
        """,
        (bucket_minutes, *params),
    )
    return {"bucket_minutes": bucket_minutes, "bucket_count": len(rows), "buckets": rows}


@mcp.tool()
def get_device_health_report(
    device_id: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    """Eksik, tekrarlı ve eşik dışı ölçümlere göre cihaz sağlık raporu üretir."""
    where_clause, params = _measurement_filter("m", device_id, start_time, end_time)
    rows = _fetch_all(
        f"""
        WITH filtered AS (
            SELECT m.*, d.name AS device_name, d.expected_interval_seconds,
                   lag(m.readtime) OVER (PARTITION BY m.device_id ORDER BY m.readtime, m.id) AS previous_time
            FROM public.measurements m
            JOIN public.devices d ON d.id = m.device_id
            WHERE {where_clause}
        ), calculated AS (
            SELECT *,
                   GREATEST(
                       floor(extract(epoch FROM (readtime - previous_time)) / expected_interval_seconds) - 1,
                       0
                   )::bigint AS missing_samples
            FROM filtered
        )
        SELECT device_id,
               device_name,
               count(*)::bigint AS measurement_count,
               count(*)::bigint - count(DISTINCT readtime)::bigint AS duplicate_row_count,
               coalesce(sum(missing_samples), 0)::bigint AS missing_sample_count,
               count(*) FILTER (WHERE current > 12)::bigint AS current_violation_count,
               count(*) FILTER (WHERE temperature > 80)::bigint AS temperature_violation_count,
               CASE
                   WHEN coalesce(sum(missing_samples), 0) > 0
                     OR count(*) - count(DISTINCT readtime) > 0
                     OR count(*) FILTER (WHERE current > 12 OR temperature > 80) > 0
                   THEN 'inceleme_gerekli'
                   ELSE 'normal'
               END AS health_status
        FROM calculated
        GROUP BY device_id, device_name
        ORDER BY device_id
        """,
        params,
    )
    return {"device_count": len(rows), "health_reports": rows}


@mcp.tool()
def list_device_events(
    device_id: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Cihaz olaylarını UTC dönemine göre, en yeni kayıtlar önce olacak biçimde listeler."""
    limit = _validated_limit(limit)
    where_clause, params = _event_filter("e", device_id, start_time, end_time)
    rows = _fetch_all(
        f"""
        SELECT e.id,
               e.device_id,
               d.name AS device_name,
               d.location,
               e.event_time,
               e.event_type,
               e.severity,
               e.title,
               e.description,
               e.resolved_at,
               e.source
        FROM public.device_events e
        JOIN public.devices d ON d.id = e.device_id
        WHERE {where_clause}
        ORDER BY e.event_time DESC, e.id DESC
        LIMIT %s
        """,
        (*params, limit + 1),
    )
    results_truncated = len(rows) > limit
    rows = rows[:limit]
    return {
        "event_count": len(rows),
        "events": rows,
        "results_truncated": results_truncated,
    }


@mcp.tool()
def get_device_event_summary(
    device_id: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    """Cihaz olaylarını cihaz, lokasyon, olay türü ve UTC saatine göre özetler."""
    where_clause, params = _event_filter("e", device_id, start_time, end_time)
    summary = _fetch_one(
        f"""
        SELECT count(*)::bigint AS event_count,
               count(*) FILTER (WHERE e.severity = 'critical')::bigint AS critical_event_count,
               count(*) FILTER (WHERE e.severity = 'warning')::bigint AS warning_event_count,
               count(*) FILTER (WHERE e.severity = 'info')::bigint AS info_event_count,
               count(*) FILTER (WHERE e.resolved_at IS NULL)::bigint AS open_event_count,
               count(*) FILTER (WHERE e.resolved_at IS NOT NULL)::bigint AS resolved_event_count,
               count(DISTINCT e.device_id)::integer AS affected_device_count,
               count(DISTINCT d.location)::integer AS location_count,
               min(e.event_time) AS first_event_time,
               max(e.event_time) AS last_event_time
        FROM public.device_events e
        JOIN public.devices d ON d.id = e.device_id
        WHERE {where_clause}
        """,
        params,
    )
    by_device = _fetch_all(
        f"""
        SELECT d.id AS device_id,
               d.name AS device_name,
               d.location,
               count(*)::bigint AS event_count,
               count(*) FILTER (WHERE e.severity = 'critical')::bigint AS critical_event_count,
               count(*) FILTER (WHERE e.resolved_at IS NULL)::bigint AS open_event_count
        FROM public.device_events e
        JOIN public.devices d ON d.id = e.device_id
        WHERE {where_clause}
        GROUP BY d.id, d.name, d.location
        ORDER BY event_count DESC, d.id
        """,
        params,
    )
    by_location = _fetch_all(
        f"""
        SELECT d.location,
               count(*)::bigint AS event_count,
               count(*) FILTER (WHERE e.severity = 'critical')::bigint AS critical_event_count,
               count(DISTINCT e.device_id)::integer AS affected_device_count
        FROM public.device_events e
        JOIN public.devices d ON d.id = e.device_id
        WHERE {where_clause}
        GROUP BY d.location
        ORDER BY event_count DESC, d.location
        """,
        params,
    )
    by_type = _fetch_all(
        f"""
        SELECT e.event_type,
               count(*)::bigint AS event_count,
               count(*) FILTER (WHERE e.severity = 'critical')::bigint AS critical_event_count
        FROM public.device_events e
        WHERE {where_clause}
        GROUP BY e.event_type
        ORDER BY event_count DESC, e.event_type
        """,
        params,
    )
    by_hour = _fetch_all(
        f"""
        SELECT extract(hour FROM e.event_time)::integer AS hour_utc,
               count(*)::bigint AS event_count
        FROM public.device_events e
        WHERE {where_clause}
        GROUP BY extract(hour FROM e.event_time)
        ORDER BY hour_utc
        """,
        params,
    )
    return {
        "filters": {
            "device_id": device_id,
            "start_time": start_time,
            "end_time": end_time,
        },
        "summary": summary,
        "by_device": by_device,
        "by_location": by_location,
        "by_type": by_type,
        "by_hour": by_hour,
    }


def _device_report_payload(
    start_time: str,
    end_time: str,
    device_id: int | None,
) -> dict[str, Any]:
    start = _parse_timestamp(start_time, "start_time")
    end = _parse_timestamp(end_time, "end_time")
    if start is None or end is None:
        raise ToolError("start_time ve end_time zorunludur.")
    if start >= end:
        raise ToolError("start_time, end_time değerinden önce olmalıdır.")
    if (end - start).days > 366:
        raise ToolError("Rapor dönemi en fazla 366 gün olabilir.")

    device: dict[str, Any] | None = None
    if device_id is not None:
        if device_id < 1:
            raise ToolError("device_id pozitif bir tam sayı olmalıdır.")
        device_rows = _fetch_all(
            """
            SELECT id AS device_id, name AS device_name, location
            FROM public.devices
            WHERE id = %s
            """,
            (device_id,),
        )
        if not device_rows:
            raise ToolError("İstenen cihaz bulunamadı.")
        device = device_rows[0]

    event_summary = get_device_event_summary(device_id, start_time, end_time)
    event_rows = list_device_events(device_id, start_time, end_time, limit=100)["events"]
    measurement_where, measurement_params = _measurement_filter(
        "m", device_id, start_time, end_time
    )
    measurement_summaries = _fetch_all(
        f"""
        SELECT d.id AS device_id,
               d.name AS device_name,
               d.location,
               count(*)::bigint AS measurement_count,
               round(avg(m.current), 3) AS average_current,
               round(avg(m.voltage), 3) AS average_voltage,
               round(avg(m.temperature), 3) AS average_temperature
        FROM public.measurements m
        JOIN public.devices d ON d.id = m.device_id
        WHERE {measurement_where}
        GROUP BY d.id, d.name, d.location
        ORDER BY d.id
        """,
        measurement_params,
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scope": {
            "start_time": start.isoformat().replace("+00:00", "Z"),
            "end_time": end.isoformat().replace("+00:00", "Z"),
            "device": device,
        },
        **event_summary,
        "events": event_rows,
        "measurement_summaries": measurement_summaries,
    }


@mcp.tool()
def generate_device_event_report(
    start_time: str,
    end_time: str,
    device_id: int | None = None,
) -> dict[str, Any]:
    """UTC dönemine ve isteğe bağlı cihaza göre görsel bir PDF olay raporu üretir."""
    payload = _device_report_payload(start_time, end_time, device_id)
    start = _parse_timestamp(start_time, "start_time")
    end = _parse_timestamp(end_time, "end_time")
    assert start is not None and end is not None

    scope_name = f"cihaz_{device_id}" if device_id is not None else "tum_cihazlar"
    generated_suffix = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = (
        f"cihaz_olay_raporu_{scope_name}_{start:%Y%m%d}_{end:%Y%m%d}_"
        f"{generated_suffix}.pdf"
    )
    output_path = REPORT_OUTPUT_DIR / filename
    try:
        create_device_event_report(output_path, payload)
    except (OSError, ValueError) as exc:
        raise ToolError("PDF raporu oluşturulamadı.") from exc

    if not output_path.is_file() or output_path.read_bytes()[:5] != b"%PDF-":
        raise ToolError("PDF raporu doğrulanamadı.")

    return {
        "report_path": str(output_path),
        "report_uri": output_path.as_uri(),
        "pdf_size_bytes": output_path.stat().st_size,
        "event_count": payload["summary"]["event_count"],
        "device_id": device_id,
        "start_time": payload["scope"]["start_time"],
        "end_time": payload["scope"]["end_time"],
    }


@mcp.resource(
    "device-events://catalog",
    name="device_event_catalog",
    title="Cihaz olay kataloğu",
    description="Cihaz olaylarının genel özetini, lokasyonlarını ve dağılımlarını JSON olarak sunar.",
    mime_type="application/json",
)
def device_event_catalog_resource() -> str:
    return json.dumps(get_device_event_summary(), ensure_ascii=False, indent=2)


@mcp.resource(
    "device-events://device/{device_id}",
    name="device_event_detail",
    title="Cihaza göre olaylar",
    description="Verilen cihaz kimliği için olay özetini ve son olayları JSON olarak sunar.",
    mime_type="application/json",
)
def device_event_detail_resource(device_id: str) -> str:
    try:
        parsed_device_id = int(device_id)
    except ValueError as exc:
        raise ToolError("device_id pozitif bir tam sayı olmalıdır.") from exc
    if parsed_device_id < 1:
        raise ToolError("device_id pozitif bir tam sayı olmalıdır.")

    payload = get_device_event_summary(device_id=parsed_device_id)
    payload["latest_events"] = list_device_events(
        device_id=parsed_device_id,
        limit=50,
    )["events"]
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.prompt(
    name="cihaz_olay_raporu",
    title="Cihaz olay raporu",
    description="Seçilen UTC dönemine ve isteğe bağlı cihaza göre olay analizi ve PDF raporu hazırlar.",
)
def device_event_report_prompt(
    start_time: str,
    end_time: str,
    device_id: str = "",
) -> str:
    device_instruction = (
        f"Yalnızca device_id={device_id} cihazını incele."
        if device_id.strip()
        else "Bütün cihazları karşılaştır; cihaz, lokasyon, olay türü ve UTC saat yoğunluğunu açıkla."
    )
    return (
        "Cihaz olay raporu hazırla. "
        f"Dönem başlangıcı {start_time}, dönem bitişi {end_time}. "
        f"{device_instruction} "
        "Önce get_device_event_summary ile özet veriyi incele. "
        "Ardından generate_device_event_report aracını aynı parametrelerle çağır. "
        "Yanıtta toplam, kritik ve açık olay sayılarını; en yoğun cihazı, lokasyonu ve UTC saat aralığını belirt. "
        "PDF dosya yolunu kullanıcıya ver ve verilerin sentetik demo verisi olduğunu açıkla."
    )


if __name__ == "__main__":
    try:
        mcp.run()
    except KeyboardInterrupt:
        pass
