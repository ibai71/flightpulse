select flight_id
from {{ ref('fact_flights') }}
where not cancelled
  and not diverted
  and arrival_delay_minutes is not null
  and (
      arrival_delayed_15 is null
      or arrival_delayed_15 not in (0, 1)
      or arrival_delayed_15 <> case when arrival_delay_minutes >= 15 then 1 else 0 end
  )
