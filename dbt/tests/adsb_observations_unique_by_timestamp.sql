select flight_id, event_ts
from {{ ref('fact_adsb_observations') }}
group by flight_id, event_ts
having count(*) > 1
