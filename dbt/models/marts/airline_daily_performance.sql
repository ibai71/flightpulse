select
    flight_date,
    airline_id,
    airline_code,
    count(*) as scheduled_flights,
    sum(case when cancelled then 1 else 0 end) as cancelled_flights,
    sum(case when diverted then 1 else 0 end) as diverted_flights,
    avg(case when not cancelled and not diverted then arrival_delay_minutes end) as average_arrival_delay_minutes,
    sum(case when not cancelled and not diverted and arrival_delay_minutes is not null then 1 else 0 end) as eligible_arrivals,
    sum(case when not cancelled and not diverted and arrival_delay_minutes < 15 then 1 else 0 end) as on_time_arrivals,
    cast(sum(case when cancelled then 1 else 0 end) as double precision) / nullif(count(*), 0) as cancellation_rate,
    cast(sum(case when diverted then 1 else 0 end) as double precision) / nullif(count(*), 0) as diversion_rate,
    cast(sum(case when not cancelled and not diverted and arrival_delay_minutes < 15 then 1 else 0 end) as double precision)
        / nullif(sum(case when not cancelled and not diverted and arrival_delay_minutes is not null then 1 else 0 end), 0) as on_time_rate
from {{ ref('fact_flights') }}
group by 1, 2, 3
