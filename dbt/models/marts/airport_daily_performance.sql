with flights as (
    select * from {{ ref('fact_flights') }}
),
departures as (
    select
        flight_date,
        origin_airport_id as airport_id,
        origin_airport_code as airport_code,
        'origin'::text as airport_role,
        count(*) as scheduled_flights,
        count(*) filter (where cancelled is true)::bigint as cancelled_flights,
        count(*) filter (where diverted is true)::bigint as diverted_flights,
        avg(departure_delay_minutes) filter (where cancelled is false) as average_delay_minutes,
        count(*) filter (where cancelled is false and departure_delay_minutes is not null)::bigint as eligible_flights,
        count(*) filter (where cancelled is false and departure_delay_minutes < 15)::bigint as on_time_flights
    from flights
    group by 1, 2, 3
),
arrivals as (
    select
        flight_date,
        destination_airport_id as airport_id,
        destination_airport_code as airport_code,
        'destination'::text as airport_role,
        count(*) as scheduled_flights,
        count(*) filter (where cancelled is true)::bigint as cancelled_flights,
        count(*) filter (where diverted is true)::bigint as diverted_flights,
        avg(arrival_delay_minutes) filter (where cancelled is false and diverted is false) as average_delay_minutes,
        count(*) filter (where cancelled is false and diverted is false and arrival_delay_minutes is not null)::bigint as eligible_flights,
        count(*) filter (where cancelled is false and diverted is false and arrival_delay_minutes < 15)::bigint as on_time_flights
    from flights
    group by 1, 2, 3
)
select
    *,
    on_time_flights::double precision / nullif(eligible_flights, 0) as on_time_rate,
    cancelled_flights::double precision / nullif(scheduled_flights, 0) as cancellation_rate,
    diverted_flights::double precision / nullif(scheduled_flights, 0) as diversion_rate
from departures
union all
select
    *,
    on_time_flights::double precision / nullif(eligible_flights, 0) as on_time_rate,
    cancelled_flights::double precision / nullif(scheduled_flights, 0) as cancellation_rate,
    diverted_flights::double precision / nullif(scheduled_flights, 0) as diversion_rate
from arrivals
