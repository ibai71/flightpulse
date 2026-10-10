{% macro iso_day_of_week(expression) -%}
  {{ return(adapter.dispatch('iso_day_of_week', 'flightpulse')(expression)) }}
{%- endmacro %}

{% macro default__iso_day_of_week(expression) -%}
  extract(isodow from {{ expression }})
{%- endmacro %}

{% macro snowflake__iso_day_of_week(expression) -%}
  dayofweekiso({{ expression }})
{%- endmacro %}

{% macro month_label(expression) -%}
  {{ return(adapter.dispatch('month_label', 'flightpulse')(expression)) }}
{%- endmacro %}

{% macro default__month_label(expression) -%}
  to_char({{ expression }}, 'FMMonth')
{%- endmacro %}

{% macro snowflake__month_label(expression) -%}
  to_char({{ expression }}, 'MMMM')
{%- endmacro %}

{% macro weekday_label(expression) -%}
  {{ return(adapter.dispatch('weekday_label', 'flightpulse')(expression)) }}
{%- endmacro %}

{% macro default__weekday_label(expression) -%}
  to_char({{ expression }}, 'FMDay')
{%- endmacro %}

{% macro snowflake__weekday_label(expression) -%}
  to_char({{ expression }}, 'DAY')
{%- endmacro %}
