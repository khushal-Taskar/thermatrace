# Algorithms

## Telemetry integration

Each sensor follows `next = current + rate × (target − current)`. Targets include low-amplitude sinusoidal background variation and controlled incident effects. Current tracks speed/load; voltage tracks SOC; power is voltage × current / 1000. SOC decreases by consumed energy over the configured time step relative to a 65 kWh demo pack. Range scales with SOC, SOH, and a thermal efficiency penalty. Motor temperature follows speed and cooling equilibrium; battery temperature follows current-dependent equilibrium. SOH stays fixed during short demonstrations.

Progress advances by `(speed × tick_seconds / 3600) / route_distance`. A piecewise interpolation between checkpoints yields GPS. Seed waypoints are expanded into OSRM road geometry and persisted; motion interpolates along that stored polyline. Accumulated tracks are bounded to 240 points. At destination, the delivery becomes delivered and the vehicle stops. Explicit reset restarts a presentation while preserving records.

## Route intelligence

Coordinates are projected into local kilometres using an equirectangular approximation around Pune. For each route segment, project the current point onto the segment, clamp the segment parameter to [0,1], and measure distance. The minimum is reported deviation. Above 0.5 km triggers intervention. Unexpected stopped-in-transit status and delay >10 minutes generate alerts. Route risk is `min(100, 20 × deviation_km + delay_minutes)`.

ETA uses remaining kilometres / current speed, with a 25 km/h assumption while stopped; it is an optimistic demo estimate rather than traffic prediction. Seeded/scenario delay is a controlled transport disruption measure, not an externally measured schedule violation.


## Cold-chain forecasting

Each medicine profile supplies minimum/maximum temperature, warning margin, excursion budget and prediction horizon. A bounded exponentially smoothed temperature slope estimates °C/min. Consecutive out-of-range ticks accumulate excursion duration; a safe measurement resets the episode timer. Remaining safe time combines projected time to the nearest boundary with the unused excursion budget and is capped at 720 minutes. Forecast temperature is `current + trend × horizon`. Crossing the band or exhausting the horizon buffer creates a predictive rule before the measured value necessarily breaches the limit. These estimates support demonstrations and require product-specific stability validation.

## OSRM routing and sensor normalization

The OSRM adapter sends latitude/longitude waypoints in OSRM longitude/latitude order, requests a full GeoJSON route, then stores normalized `[latitude, longitude]` points, road distance and duration. On request failure the transaction preserves the stored route. MQTT ingestion requires a registered active device mapped to one vehicle, merges only allowlisted telemetry fields, recomputes cold-chain and risk outputs, and persists the full snapshot with `synthetic=false`.

## Incident episodes

For each tick, compare breached rule types against active episodes for that vehicle. Create missing episodes; refresh existing last-seen values/snapshot; reset acknowledgement on severity change; mark disappeared conditions inactive. A recurrence after recovery creates a new episode. Acknowledgement stores user/time but does not dismiss a continuing unsafe measurement.

## History and reports

History uses chronological row ranks and an adaptive stride to sample approximately 600 evenly distributed points over the complete chosen range, retaining endpoints. Reports calculate count/min/max/mean directly from all eligible database rows. Thus charts remain bounded without biasing report aggregates toward recent records or chart-selected points.

## Risk pipeline

See `AI_METHODOLOGY.md` for fitted models and combination equations. Complexity is linear in the number of vehicles for a tick, multiplied by fixed tree prediction costs; the map geometry is linear in the small checkpoint count. The five-vehicle, single-worker deployment is the validated scope.

## Voice reachability and call notes

Vehicle reachability compares BMS estimated range with delivery distance. Cold-chain margin compares remaining safe time with route-duration-scaled remaining progress plus recorded delay. A margin of at least 10 km and 10 minutes yields `LIKELY_TO_REACH`; non-negative margins yield `MAY_REACH_WITH_RISK`; a negative battery or cold-chain margin yields `INTERVENTION_REQUIRED`. This is an explainable operational heuristic, not a guarantee.

At call close, deterministic topic matching classifies battery, cold-chain, route/ETA, and risk discussion. The note records current SOC, battery/container temperature, remaining distance, risk score, active factors and recommended actions. Raw audio is deleted after each transcription turn; only messages and the structured note are retained.
