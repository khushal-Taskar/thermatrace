"""Local hybrid risk engine. ML is trained on disclosed synthetic data, not clinical outcomes."""
import numpy as np
import pandas as pd
from pathlib import Path
import joblib
from sklearn.ensemble import IsolationForest, RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
from ..config import settings

FEATURES = ["soc", "soh", "battery_temperature", "motor_temperature", "pack_current", "speed", "temperature", "humidity", "shock_level", "route_deviation_distance", "delay_minutes", "distance_remaining", "temperature_trend_c_per_minute", "excursion_duration_minutes", "remaining_safe_time_minutes", "predicted_temperature"]
BASELINE = [70, 96, 31, 52, 40, 45, 5, 48, 0.3, 0, 0, 30, 0, 0, 120, 5]


def feature_row(snapshot):
    values = {**snapshot["vehicle"], **snapshot["battery"], **snapshot["container"], **snapshot["delivery"]}
    return [values[name] for name in FEATURES]


def synthetic_training(seed=42, n=3500):
    rng = np.random.default_rng(seed)
    soc = rng.uniform(5, 100, n)
    speed = rng.uniform(0, 80, n)
    current = speed * 0.85 + rng.normal(8, 6, n)
    battery_temp = 27 + current * 0.11 + rng.normal(0, 2, n)
    motor_temp = 34 + speed * 0.42 + rng.normal(0, 4, n)
    temp = rng.normal(5, .8, n)
    humidity = rng.normal(48, 7, n)
    shock = rng.uniform(.1, .8, n)
    deviation = rng.uniform(0, .08, n)
    delay = rng.uniform(0, 3, n)
    abnormal = rng.random(n) < .45
    battery_temp += abnormal * rng.uniform(0, 28, n)
    motor_temp += abnormal * rng.uniform(0, 60, n)
    temp += abnormal * rng.uniform(-7, 12, n)
    humidity += abnormal * rng.uniform(0, 40, n)
    shock += abnormal * rng.uniform(0, 5, n)
    deviation += abnormal * rng.uniform(0, 6, n)
    delay += abnormal * rng.uniform(0, 50, n)
    distance = rng.uniform(5, 160, n)
    trend=rng.normal(0,.025,n)+abnormal*rng.normal(.05,.09,n)
    excursion=np.maximum(0,np.abs(temp-5)-3)*rng.uniform(2,18,n)
    remaining=np.clip(30-excursion+np.where(abs(trend)>.005,np.maximum(0,(8-temp)/np.maximum(trend,.005)),120),0,720)
    predicted=temp+trend*15
    frame = pd.DataFrame(np.column_stack([soc, rng.uniform(82, 100, n), battery_temp, motor_temp, current, speed, temp, humidity, shock, deviation, delay, distance, trend, excursion, remaining, predicted]), columns=FEATURES)
    # Synthetic hazard target: battery margin, thermal exposure, transport disturbance.
    penalties = np.column_stack([
        np.maximum(0, 25-soc)*1.6,
        np.maximum(0, battery_temp-40)*2.5,
        np.maximum(0, motor_temp-80)*1.2,
        np.maximum(0, temp-8)*9 + np.maximum(0, 2-temp)*9,
        np.maximum(0, humidity-65)*.8,
        np.maximum(0, shock-1.5)*9,
        np.maximum(0, deviation-.4)*6,
        np.maximum(0, delay-10)*.6,
        np.maximum(0, distance - soc*2.4)*.3,
        np.maximum(0,15-remaining)*2.2,
        np.maximum(0,excursion-15)*1.2,
        (np.maximum(0,predicted-8)+np.maximum(0,2-predicted))*5,
    ])
    target = np.clip(8 + penalties.max(axis=1) + penalties.sum(axis=1)*.2, 0, 100)
    normal = frame[(~abnormal) & (soc>35) & (distance<soc*2.4)]
    return frame, target, normal


class RiskEngine:
    def __init__(self):
        bundle_path=Path(settings.model_bundle_path)
        if bundle_path.exists():
            bundle=joblib.load(bundle_path)
            if bundle.get("features")!=FEATURES:
                raise ValueError("Validated model feature schema does not match this application version")
            self.anomaly_model=bundle["anomaly_model"]
            self.risk_model=bundle["risk_model"]
            self.metadata={**bundle["metadata"],"features":FEATURES,"anomaly_model":"Isolation Forest","risk_model":"Random Forest regressor"}
            return
        frame, target, normal = synthetic_training()
        train, test, y_train, y_test = train_test_split(frame, target, test_size=.2, random_state=42)
        self.anomaly_model = IsolationForest(n_estimators=100, contamination=.04, random_state=42, n_jobs=1).fit(normal)
        self.risk_model = RandomForestRegressor(n_estimators=70, max_depth=12, random_state=42, n_jobs=1).fit(train, y_train)
        self.metadata = {"training_source": "Synthetic transport telemetry; educational simulation only", "training_samples": len(train), "holdout_samples": len(test), "synthetic_holdout_mae": round(mean_absolute_error(y_test, self.risk_model.predict(test)), 2), "anomaly_model": "Isolation Forest", "risk_model": "Random Forest regressor", "features": FEATURES, "version": "hybrid-2.0-cold-chain", "labelled_data_status":"AWAITING_VALIDATED_DATA", "limitation": "Scores are prioritization estimates, not validated probabilities of spoilage or failure."}

    def evaluate(self, snapshot):
        v, b, c, d = (snapshot[k] for k in ["vehicle", "battery", "container", "delivery"])
        rules = []

        def detect(condition, code, severity, points, feature, value, threshold, reason, action):
            if condition:
                rules.append({"type": code, "severity": severity, "points": points, "feature": feature, "value": value, "threshold": threshold, "reason": reason, "recommended_action": action})

        detect(b["soc"]<25, "LOW_SOC", "CRITICAL" if b["soc"]<15 else "HIGH", 86 if b["soc"]<15 else 64, "soc", b["soc"], "≥25%", f"Battery charge is {b['soc']:.1f}%", "Check range margin and divert to a charging or replacement vehicle point.")
        detect(b["estimated_range"]<d["distance_remaining"]+10, "INSUFFICIENT_RANGE", "HIGH", 67, "estimated_range", b["estimated_range"], f">{d['distance_remaining']+10:.1f} km", "Estimated range does not cover the route with a 10 km reserve", "Arrange a vehicle transfer before battery depletion.")
        detect(b["battery_temperature"]>43, "BATTERY_OVERHEAT", "CRITICAL" if b["battery_temperature"]>48 else "HIGH", 88 if b["battery_temperature"]>48 else 68, "battery_temperature", b["battery_temperature"], "≤43°C", f"Battery temperature is {b['battery_temperature']:.1f}°C", "Stop safely, reduce load, and inspect the battery cooling system.")
        detect(v["motor_temperature"]>85, "MOTOR_OVERHEAT", "CRITICAL" if v["motor_temperature"]>100 else "HIGH", 86 if v["motor_temperature"]>100 else 65, "motor_temperature", v["motor_temperature"], "≤85°C", f"Motor temperature is {v['motor_temperature']:.1f}°C", "Reduce speed and inspect motor cooling at a safe stop.")
        excursion = c["temperature"]<c["min_temperature"] or c["temperature"]>c["max_temperature"]
        gap = max(c["min_temperature"]-c["temperature"], c["temperature"]-c["max_temperature"], 0)
        prolonged=c.get("excursion_duration_minutes",0)>=c.get("max_excursion_minutes",30)
        detect(excursion, "TEMPERATURE_EXCURSION", "CRITICAL" if gap>1 or prolonged else "HIGH", 92 if prolonged else 90 if gap>1 else 70, "temperature", c["temperature"], f"{c['min_temperature']}–{c['max_temperature']}°C", f"Container temperature {c['temperature']:.1f}°C is outside its {c.get('profile_name','configured')} band for {c.get('excursion_duration_minutes',0):.1f} minutes", "Restore refrigeration; quarantine affected shipment for product-specific quality review.")
        predictive=c.get("predicted_excursion",False) and not excursion
        remaining=c.get("remaining_safe_time_minutes",720)
        detect(predictive, "PREDICTIVE_TEMPERATURE_ALERT", "HIGH" if remaining<=10 else "WARNING", 64 if remaining<=10 else 46, "predicted_temperature", c.get("predicted_temperature",c["temperature"]), f"{c['min_temperature']}–{c['max_temperature']}°C", f"Temperature trend predicts {c.get('predicted_temperature',c['temperature']):.1f}°C within {c.get('prediction_horizon_minutes',15)} minutes; estimated safe-time buffer is {remaining:.1f} minutes", "Inspect refrigeration now and prepare an intervention before the product-specific limit is crossed.")
        detect(c["humidity"]>65, "HIGH_HUMIDITY", "HIGH" if c["humidity"]>80 else "WARNING", 65 if c["humidity"]>80 else 40, "humidity", c["humidity"], "≤65%", f"Container humidity is {c['humidity']:.1f}%", "Inspect seals and desiccant; verify packaging integrity.")
        detect(c["door_status"]=="OPEN", "DOOR_OPEN", "HIGH", 66, "door_status", c["door_status"], "CLOSED", "Container door is open during transport", "Close the door and check temperature recovery.")
        detect(c["tamper_status"]=="DETECTED", "TAMPERING", "CRITICAL", 94, "tamper_status", c["tamper_status"], "CLEAR", "Container seal tampering detected", "Secure the shipment and initiate a custody investigation.")
        detect(c["shock_level"]>2, "SHOCK_EVENT", "HIGH", 69, "shock_level", c["shock_level"], "≤2g", f"Handling shock reached {c['shock_level']:.1f}g", "Inspect fragile pharmaceutical packaging and record the incident.")
        detect(d["route_deviation_distance"]>.5, "ROUTE_DEVIATION", "HIGH", 64, "route_deviation_distance", d["route_deviation_distance"], "≤0.5 km", f"Vehicle is {d['route_deviation_distance']:.2f} km off its planned route", "Contact driver and verify the deviation and shipment security.")
        detect(d["delay_minutes"]>10, "DELIVERY_DELAY", "WARNING", 42, "delay_minutes", d["delay_minutes"], "≤10 min", f"Delivery is delayed {d['delay_minutes']:.1f} minutes", "Notify receiving facility and review remaining cooling capacity.")
        detect(v["vehicle_status"]=="FAULT", "VEHICLE_FAILURE", "CRITICAL", 92, "vehicle_status", v["vehicle_status"], "RUNNING / IDLE", "Vehicle drivetrain failure", "Dispatch roadside support and protect the cold chain with a vehicle transfer.")
        detect(b["bms_fault"]!="NONE", "BMS_FAULT", "CRITICAL", 91, "bms_fault", b["bms_fault"], "NONE", f"BMS fault: {b['bms_fault']}", "Stop safely and request qualified battery-system inspection.")
        detect(v["vehicle_status"]=="STOPPED" and d["delivery_status"]!="DELIVERED", "UNEXPECTED_STOP", "WARNING", 38, "speed", v["speed"], ">0 km/h in transit", "Unexpected stop during an active delivery", "Contact the driver and verify ETA and cooling availability.")
        row = pd.DataFrame([feature_row(snapshot)], columns=FEATURES)
        anomaly_margin = float(self.anomaly_model.decision_function(row)[0])
        anomaly_score = round(float(np.clip(-anomaly_margin * 240 + 12, 0, 100)), 1)
        prediction = float(self.risk_model.predict(row)[0])
        floor = max([r["points"] for r in rules] or [0])
        score = int(round(min(100, max(floor, prediction*.8+anomaly_score*.2) + min(8, max(0, len(rules)-1)*2))))
        level = "NORMAL" if score<=30 else "WARNING" if score<=60 else "HIGH" if score<=80 else "CRITICAL"
        # Counterfactual model contributions: replace each feature with the nominal baseline.
        rows = np.tile(row.to_numpy(), (len(FEATURES), 1))
        for i, nominal in enumerate(BASELINE):
            rows[i, i] = nominal
        changed = self.risk_model.predict(pd.DataFrame(rows, columns=FEATURES))
        contributions = sorted([{ "feature": name, "contribution": round(max(0, prediction-float(changed[i])), 1), "value": float(row.iloc[0, i]) } for i,name in enumerate(FEATURES)], key=lambda x:x["contribution"], reverse=True)
        rules.sort(key=lambda x:x["points"], reverse=True)
        reason = "; ".join(r["reason"] for r in rules[:4]) if rules else ("Unusual combination of telemetry detected by Isolation Forest" if anomaly_margin<0 else "Telemetry is within the configured operational safety envelope")
        return {"risk_score": score, "risk_level": level, "reason": reason, "recommended_action": rules[0]["recommended_action"] if rules else ("Review current telemetry and compare with recent history." if score>30 else "Continue monitoring the delivery."), "contributing_factors": rules, "feature_contributions": contributions, "anomaly_score": anomaly_score, "is_anomaly": anomaly_margin<0, "model_prediction": round(prediction, 1), "rule_floor": floor, "uncertainty": self.metadata["limitation"], "detected_at": snapshot["timestamp"]}
