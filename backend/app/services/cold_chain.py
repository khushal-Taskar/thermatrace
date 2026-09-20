"""Medicine-specific cold-chain calculations for simulated and sensor telemetry."""
from types import SimpleNamespace


def profile_or_default(container, profile=None):
    return profile or SimpleNamespace(
        id="FALLBACK",
        name=f"{container.min_temperature:g}-{container.max_temperature:g} C fallback",
        min_temperature=container.min_temperature,
        max_temperature=container.max_temperature,
        warning_margin=.7,
        max_excursion_minutes=30,
        prediction_horizon_minutes=15,
        handling_notes="Fallback demonstration limits; verify manufacturer stability instructions.",
        validated=False,
    )


def cold_chain_metrics(container, profile, temperature, previous_temperature, state, interval_seconds):
    profile=profile_or_default(container,profile)
    step_minutes=max(interval_seconds/60,1/60)
    raw_rate=(temperature-previous_temperature)/step_minutes
    # Container probes are sampled every few seconds; bounding and strongly
    # smoothing the minute rate prevents sensor quantisation from becoming a
    # false 10–15 minute excursion forecast while retaining sustained drift.
    raw_rate=max(-.12,min(.12,raw_rate))
    previous_rate=max(-.12,min(.12,float(state.get("temperature_trend_c_per_minute",0))))
    trend=previous_rate*.8+raw_rate*.2
    outside=temperature<profile.min_temperature or temperature>profile.max_temperature
    excursion=float(state.get("excursion_duration_minutes",0))
    excursion=excursion+step_minutes if outside else 0
    if outside:
        time_to_boundary=0
    elif trend>.005:
        time_to_boundary=max(0,(profile.max_temperature-temperature)/trend)
    elif trend<-.005:
        time_to_boundary=max(0,(temperature-profile.min_temperature)/abs(trend))
    else:
        time_to_boundary=720
    remaining=max(0,min(720,time_to_boundary+profile.max_excursion_minutes-excursion))
    predicted=temperature+trend*profile.prediction_horizon_minutes
    predicted_excursion=predicted<profile.min_temperature or predicted>profile.max_temperature
    near_limit=(temperature-profile.min_temperature)<profile.warning_margin or (profile.max_temperature-temperature)<profile.warning_margin
    status="ALERT" if predicted_excursion or remaining<=profile.prediction_horizon_minutes else "WATCH" if near_limit else "SAFE"
    return {
        "profile_id":profile.id,
        "profile_name":profile.name,
        "profile_validated":profile.validated,
        "warning_margin":profile.warning_margin,
        "max_excursion_minutes":profile.max_excursion_minutes,
        "prediction_horizon_minutes":profile.prediction_horizon_minutes,
        "handling_notes":profile.handling_notes,
        "excursion_duration_minutes":round(excursion,2),
        "remaining_safe_time_minutes":round(remaining,1),
        "temperature_trend_c_per_minute":round(trend,3),
        "predicted_temperature":round(predicted,2),
        "predictive_status":status,
        "predicted_excursion":predicted_excursion,
        "outside_safe_range":outside,
    }
