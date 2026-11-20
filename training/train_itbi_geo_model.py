"""
train_itbi_geo_model.py — Modelo ITBI GEO-ONLY (piso de último recurso).

Usa só área + coordenada + distâncias de landmarks — SEM setor e SEM SQL. Serve
como piso para imóveis cujo edital não publica a Inscrição/SQL (nem quadra),
usando a coordenada geocodificada do bairro. É o tier mais grosseiro (menos
preciso que o cadastral), mas garante um piso para ~todos os imóveis.

Treinado no preço transacionado real (ITBI 2024).
"""

import json
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GridSearchCV, KFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from auction_intel.features import engineering as features

ITBI = "datasets/itbi_2024_apartments.csv"
COORDS = "datasets/quadra_coords.csv"
OUT = "models/itbi_geo_model.pkl"
REPORT = "models/itbi_geo_model_report.json"
RS = 42
NUM = ["area", "log_area", "latitude", "longitude"] + list(features.ALL_LANDMARKS.keys())


def main():
    df = pd.read_csv(ITBI)
    df["quadra6"] = df["sql"].astype("Int64").astype(str).str.zfill(11).str[:6]
    co = pd.read_csv(COORDS, dtype={"quadra6": str}).drop_duplicates("quadra6")
    df = df.merge(co[["quadra6", "latitude", "longitude"]], on="quadra6", how="left").dropna(
        subset=["latitude", "longitude"]
    )
    df = features.add_engineered(df)
    X, y = df[NUM], np.log1p(df["price"])
    print(f"{len(df)} apartamentos.")

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=RS)
    pipe = Pipeline(
        [
            ("sc", StandardScaler()),
            (
                "hgb",
                HistGradientBoostingRegressor(
                    max_iter=600,
                    early_stopping=True,
                    validation_fraction=0.1,
                    n_iter_no_change=20,
                    random_state=RS,
                ),
            ),
        ]
    )
    grid = {
        "hgb__learning_rate": [0.05, 0.1],
        "hgb__max_depth": [None, 12],
        "hgb__max_leaf_nodes": [31, 63],
        "hgb__l2_regularization": [0.0, 1.0],
    }
    t0 = time.time()
    gs = GridSearchCV(
        pipe, grid, scoring="r2", cv=KFold(5, shuffle=True, random_state=RS), n_jobs=-1
    )
    gs.fit(Xtr, ytr)
    model = gs.best_estimator_
    pred = model.predict(Xte)
    r2 = r2_score(yte, pred)
    pr, tr = np.expm1(pred), np.expm1(yte)
    mae, mape = mean_absolute_error(tr, pr), float(np.mean(np.abs((tr - pr) / tr)) * 100)
    print(
        f"busca {time.time() - t0:.0f}s | CV R²={gs.best_score_:.4f} | holdout R²={r2:.4f} | MAPE {mape:.1f}%"
    )

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    metrics = {
        "r2_test": round(float(r2), 4),
        "r2_cv": round(float(gs.best_score_), 4),
        "mae": round(float(mae)),
        "mape": round(mape, 2),
    }
    joblib.dump(
        {
            "model": model,
            "landmarks": features.ALL_LANDMARKS,
            "num_features": NUM,
            "metrics": metrics,
            "version": f"itbi_geo_r2_{r2:.4f}",
            "notes": "Geo-only (area+coord). Piso de ultimo recurso, sem SQL.",
        },
        OUT,
    )
    json.dump(metrics, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"💾 {OUT}")


if __name__ == "__main__":
    main()
