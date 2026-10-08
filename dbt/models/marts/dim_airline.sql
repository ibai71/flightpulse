select
    airline_id,
    max(airline_code) as airline_code
from {{ ref('stg_bts_flights') }}
where airline_id is not null
group by airline_id
