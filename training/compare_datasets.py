"""
compare_datasets.py — Comparativo justo de bases de treino.

Roda a MESMA arquitetura (TargetEncoder + StandardScaler + HGB com os
hiperparâmetros afinados numa busca coarse-to-fine anterior) e o MESMO protocolo (KFold 5 +
holdout) em vários cenários, isolando o efeito do DADO.

Cenários:
  A_native_parity   base atual, coords reais (por imóvel)
  A_centroid_parity base atual, coords = centroide do bairro (geo comparável à 2024)
  B_apts_parity     2024 só apartamentos, features de paridade
  B_all_parity      2024 apês+casas, features de paridade
  B_apts_rich       2024 só apartamentos + IPTU/condomínio/comodidades
  B_all_rich        2024 apês+casas + features ricas
  C_apts_parity     combinada (A_centroid + B_apts), paridade
  C_all_parity      combinada (A_centroid + B_all), paridade

Métrica primária: R² médio em validação cruzada (5-fold). Também holdout
R²/MAE/MAPE em R$ reais.
"""
import json
import re
import unicodedata

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, TargetEncoder

from auction_intel.features import engineering as features

BASE_ATUAL = "datasets/dataset_under_7M.csv"
BASE_2024 = "datasets/sp2024_normalized.csv"
RS = 42

# Hiperparâmetros afinados (busca coarse-to-fine anterior)
HGB_PARAMS = dict(
    learning_rate=0.06, max_depth=None, max_leaf_nodes=63, l2_regularization=0.0,
    max_iter=600, early_stopping=True, validation_fraction=0.1,
    n_iter_no_change=20, random_state=RS,
)
RICH_EXTRA = ["iptu", "condo", "n_amenities"]


def norm_district(s):
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^a-zA-Z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def make_pipeline(numeric_cols):
    pre = ColumnTransformer([
        ("district_te", TargetEncoder(target_type="continuous", random_state=RS), ["district"]),
        ("num", StandardScaler(), numeric_cols),
    ], remainder="drop")
    return Pipeline([("pre", pre), ("hgb", HistGradientBoostingRegressor(**HGB_PARAMS))])


def prep(df, extra_numeric=None):
    """Aplica engenharia de features e devolve (X, y, numeric_cols)."""
    df = features.add_engineered(df)
    df["district"] = df["district"].map(norm_district)
    numeric_cols = features.numeric_features() + (extra_numeric or [])
    X = df[numeric_cols + ["district"]]
    y = np.log1p(df["price"])
    return X, y, numeric_cols


def evaluate(name, df, extra_numeric=None):
    X, y, numeric_cols = prep(df, extra_numeric)
    pipe = make_pipeline(numeric_cols)

    cv = KFold(n_splits=5, shuffle=True, random_state=RS)
    cv_r2 = cross_val_score(pipe, X, y, cv=cv, scoring="r2", n_jobs=-1)

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=RS)
    pipe.fit(Xtr, ytr)
    pred = pipe.predict(Xte)
    r2 = r2_score(yte, pred)
    pr, tr = np.expm1(pred), np.expm1(yte)
    mae = mean_absolute_error(tr, pr)
    mape = float(np.mean(np.abs((tr - pr) / tr)) * 100)

    res = {"scenario": name, "n": len(df), "cv_r2_mean": round(cv_r2.mean(), 4),
           "cv_r2_std": round(cv_r2.std(), 4), "holdout_r2": round(float(r2), 4),
           "mae": round(float(mae), 0), "mape": round(mape, 2)}
    print(f"  {name:<20} n={len(df):>6} | CV R²={res['cv_r2_mean']:.4f}±{res['cv_r2_std']:.4f}"
          f" | holdout R²={res['holdout_r2']:.4f} | MAE R$ {mae:>10,.0f} | MAPE {mape:5.1f}%")
    return res


def to_centroid_geo(a):
    """Substitui lat/lon reais da base atual pelo centroide do bairro."""
    a = a.copy()
    a["dnorm"] = a["district"].map(norm_district)
    cen = a.groupby("dnorm")[["latitude", "longitude"]].transform("mean")
    a["latitude"], a["longitude"] = cen["latitude"], cen["longitude"]
    return a


def main():
    a = pd.read_csv(BASE_ATUAL)
    b = pd.read_csv(BASE_2024)
    a_cen = to_centroid_geo(a)
    b_apts = b[b.category == "Apartamentos"].copy()
    parity = ["area", "bedrooms", "bathrooms", "garage", "latitude", "longitude", "district", "price"]

    print("=" * 110)
    print("COMPARATIVO DE BASES (mesmo modelo, mesmo protocolo)")
    print("=" * 110)
    results = []
    results.append(evaluate("A_native_parity", a))
    results.append(evaluate("A_centroid_parity", a_cen))
    results.append(evaluate("B_apts_parity", b_apts[parity]))
    results.append(evaluate("B_all_parity", b[parity]))
    results.append(evaluate("B_apts_rich", b_apts, extra_numeric=RICH_EXTRA))
    results.append(evaluate("B_all_rich", b, extra_numeric=RICH_EXTRA))
    results.append(evaluate("C_apts_parity", pd.concat([a_cen[parity], b_apts[parity]], ignore_index=True)))
    results.append(evaluate("C_all_parity", pd.concat([a_cen[parity], b[parity]], ignore_index=True)))

    results.sort(key=lambda r: r["cv_r2_mean"], reverse=True)
    print("\n" + "=" * 110)
    print("RANKING por CV R² (validação cruzada, métrica primária):")
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r['scenario']:<20} CV R²={r['cv_r2_mean']:.4f} | holdout={r['holdout_r2']:.4f} | MAPE {r['mape']}%")

    with open("compare_datasets_report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\n📝 Relatório salvo: compare_datasets_report.json")


if __name__ == "__main__":
    main()
