with ranked_observations as (
    select
        flight_id,
        icao24,
        callsign,
        icao_type,
        operator_name,
        start_airport_ident,
        end_airport_ident,
        event_ts,
        event_epoch,
        longitude,
        latitude,
        altitude_ft,
        track_deg,
        ground_speed_knots,
        vertical_rate_fpm,
        indicated_airspeed_knots,
        height_agl_ft,
        row_number() over (partition by flight_id, event_ts order by event_epoch) as row_num
    from {{ ref('stg_adsb_observations') }}
)
select
    flight_id,
    icao24,
    callsign,
    icao_type,
    operator_name,
    start_airport_ident,
    end_airport_ident,
    event_ts,
    event_epoch,
    longitude,
    latitude,
    altitude_ft,
    track_deg,
    ground_speed_knots,
    vertical_rate_fpm,
    indicated_airspeed_knots,
    height_agl_ft
from ranked_observations
where row_num = 1
