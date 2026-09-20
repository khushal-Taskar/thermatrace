"""Reproducible retraining and validation pipeline for future labelled telemetry."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score, recall_score
from sklearn.model_selection import train_test_split
from .engine import FEATURES

TARGET="risk_target"


def validate_labelled_frame(frame):
    missing=[column for column in [*FEATURES,TARGET] if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing labelled-data columns: {', '.join(missing)}")
    clean=frame[[*FEATURES,TARGET]].replace([np.inf,-np.inf],np.nan).dropna()
    if len(clean)<100:
        raise ValueError("At least 100 complete labelled records are required")
    if not clean[TARGET].between(0,100).all():
        raise ValueError("risk_target must be between 0 and 100")
    if (clean[TARGET]<=30).sum()<20 or (clean[TARGET]>=61).sum()<20:
        raise ValueError("Data needs at least 20 normal and 20 high/critical labelled records")
    return clean


def train_validated_bundle(csv_path,output_path,version=None):
    clean=validate_labelled_frame(pd.read_csv(csv_path))
    x=clean[FEATURES];y=clean[TARGET]
    train_x,test_x,train_y,test_y=train_test_split(x,y,test_size=.2,random_state=42,stratify=pd.cut(y,[-1,30,60,80,100],labels=False))
    normal=train_x[train_y<=30]
    anomaly=IsolationForest(n_estimators=180,contamination="auto",random_state=42,n_jobs=1).fit(normal)
    risk=RandomForestRegressor(n_estimators=220,max_depth=14,min_samples_leaf=2,random_state=42,n_jobs=1).fit(train_x,train_y)
    predictions=np.clip(risk.predict(test_x),0,100)
    metrics={
        "mae":round(float(mean_absolute_error(test_y,predictions)),3),
        "r2":round(float(r2_score(test_y,predictions)),3),
        "high_risk_recall":round(float(recall_score(test_y>=61,predictions>=61,zero_division=0)),3),
        "train_samples":len(train_x),"holdout_samples":len(test_x),"total_samples":len(clean),
    }
    version=version or datetime.now(timezone.utc).strftime("labelled-%Y%m%d-%H%M%S")
    bundle={"features":FEATURES,"anomaly_model":anomaly,"risk_model":risk,"metadata":{"version":version,"training_source":"User-supplied labelled transport telemetry","labelled_data_status":"VALIDATED_HOLDOUT","validation_metrics":metrics,"training_samples":len(train_x),"holdout_samples":len(test_x),"limitation":"Holdout metrics apply only to the supplied labelled dataset and deployment population."}}
    output=Path(output_path);output.parent.mkdir(parents=True,exist_ok=True);joblib.dump(bundle,output)
    return {**bundle["metadata"],"artifact_path":str(output)}


def main():
    parser=argparse.ArgumentParser(description="Train and validate the ThermaTrace risk models from labelled CSV telemetry")
    parser.add_argument("csv_path");parser.add_argument("--output",default="data/models/validated-risk-model.joblib");parser.add_argument("--version")
    args=parser.parse_args();print(train_validated_bundle(args.csv_path,args.output,args.version))


if __name__=="__main__":
    main()

