select
    flight_date,
    airline_id,
    airline_code,
    count(*) as scheduled_flights,
    count(*) filter (where cancelled is true)::bigint as cancelled_flights,
    count(*) filter (where diverted is true)::bigint as diverted_flights,
    avg(arrival_delay_minutes) filter (where cancelled is false and diverted is false) as average_arrival_delay_minutes,
    count(*) filter (where cancelled is false and diverted is false and arrival_delay_minutes is not null)::bigint as eligible_arrivals,
    count(*) filter (where cancelled is false and diverted is false and arrival_delay_minutes < 15)::bigint as on_time_arrivals,
    count(*) filter (where cancelled is true)::double precision / nullif(count(*), 0) as cancellation_rate,
    count(*) filter (where diverted is true)::double precision / nullif(count(*), 0) as diversion_rate,
    count(*) filter (where cancelled is false and diverted is false and arrival_delay_minutes < 15)::double precision
        / nullif(count(*) filter (where cancelled is false and diverted is false and arrival_delay_minutes is not null), 0) as on_time_rate
from {{ ref('fact_flights') }}
group by 1, 2, 3
