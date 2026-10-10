with flights as (
    select * from {{ ref('fact_flights') }}
),
departures as (
    select
        flight_date,
        origin_airport_id as airport_id,
        origin_airport_code as airport_code,
        'origin' as airport_role,
        count(*) as scheduled_flights,
        sum(case when cancelled then 1 else 0 end) as cancelled_flights,
        sum(case when diverted then 1 else 0 end) as diverted_flights,
        avg(case when not cancelled then departure_delay_minutes end) as average_delay_minutes,
        sum(case when not cancelled and departure_delay_minutes is not null then 1 else 0 end) as eligible_flights,
        sum(case when not cancelled and departure_delay_minutes < 15 then 1 else 0 end) as on_time_flights
    from flights
    group by 1, 2, 3
),
arrivals as (
    select
        flight_date,
        destination_airport_id as airport_id,
        destination_airport_code as airport_code,
        'destination' as airport_role,
        count(*) as scheduled_flights,
        sum(case when cancelled then 1 else 0 end) as cancelled_flights,
        sum(case when diverted then 1 else 0 end) as diverted_flights,
        avg(case when not cancelled and not diverted then arrival_delay_minutes end) as average_delay_minutes,
        sum(case when not cancelled and not diverted and arrival_delay_minutes is not null then 1 else 0 end) as eligible_flights,
        sum(case when not cancelled and not diverted and arrival_delay_minutes < 15 then 1 else 0 end) as on_time_flights
    from flights
    group by 1, 2, 3
)
select
    *,
    cast(on_time_flights as double precision) / nullif(eligible_flights, 0) as on_time_rate,
    cast(cancelled_flights as double precision) / nullif(scheduled_flights, 0) as cancellation_rate,
    cast(diverted_flights as double precision) / nullif(scheduled_flights, 0) as diversion_rate
from departures
union all
select
    *,
    cast(on_time_flights as double precision) / nullif(eligible_flights, 0) as on_time_rate,
    cast(cancelled_flights as double precision) / nullif(scheduled_flights, 0) as cancellation_rate,
    cast(diverted_flights as double precision) / nullif(scheduled_flights, 0) as diversion_rate
from arrivals
