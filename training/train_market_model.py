"""
train_market_model.py — Modelo de valor de mercado (base de anúncios de 2024).

Baseado no comparativo (compare_datasets.py), a melhor base IMPLANTÁVEL — isto
é, usando só as features que o scraper de leilão consegue fornecer
(area, quartos, banheiros, vagas, bairro → lat/lon) — é a de 2024 restrita a
APARTAMENTOS. Ela salta o R² de ~0.78 (base antiga) para ~0.885.

As features ricas (IPTU/condomínio/comodidades) rendem mais (~0.90), mas NÃO são
obtidas no scraping de leilão, então ficam fora do modelo de produção.

Consistência treino/inferência:
  * engenharia de features vem de `auction_intel.features.engineering` (a mesma da inferência);
  * a normalização de bairro é EMBUTIDA no Pipeline via FunctionTransformer, de
    modo que o bairro cru do scraper é normalizado internamente antes do
    TargetEncoder — sem train/serve skew.

Busca de hiperparâmetros coarse-to-fine + cross-validation (KFold 5).
Salva em `models/market_model.pkl` e o relatório em `models/market_model_report.json`.
Rodar da raiz do repositório: python training/train_market_model.py
"""

import json
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GridSearchCV, KFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler, TargetEncoder

from auction_intel.features import engineering as features

INPUT_FILE = "datasets/sp2024_normalized.csv"
OUTPUT_PKL = "models/market_model.pkl"
REPORT_JSON = "models/market_model_report.json"
BASELINE_A_R2 = 0.7788  # base antiga (A_native_parity, CV R²) — referência
RS = 42


def build_pipeline() -> Pipeline:
    num_cols = features.numeric_features()
    district_pipe = Pipeline(
        [
            (
                "norm",
                FunctionTransformer(
                    features.normalize_district_frame, feature_names_out="one-to-one"
                ),
            ),
            ("te", TargetEncoder(target_type="continuous", random_state=RS)),
        ]
    )
    pre = ColumnTransformer(
        [
            ("district", district_pipe, ["district"]),
            ("num", StandardScaler(), num_cols),
        ],
        remainder="drop",
    )
    hgb = HistGradientBoostingRegressor(
        max_iter=600,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=20,
        random_state=RS,
    )
    return Pipeline([("pre", pre), ("hgb", hgb)])


def coarse_grid():
    return {
        "hgb__learning_rate": [0.03, 0.05, 0.10],
        "hgb__max_depth": [None, 6, 12],
        "hgb__max_leaf_nodes": [31, 63],
        "hgb__l2_regularization": [0.0, 1.0],
    }


def refine_grid(best):
    lr, md = best["hgb__learning_rate"], best["hgb__max_depth"]
    mln, l2 = best["hgb__max_leaf_nodes"], best["hgb__l2_regularization"]
    lr_grid = sorted({round(max(0.005, lr * f), 4) for f in (0.6, 1.0, 1.5)})
    mln_grid = sorted({max(15, int(mln * f)) for f in (0.75, 1.0, 1.5)})
    md_grid = [None, 10, 16] if md is None else sorted({max(2, md - 3), md, md + 4})
    l2_grid = sorted({0.0, l2, round(l2 + 0.5, 2)}) if l2 > 0 else [0.0, 0.5, 1.0]
    return {
        "hgb__learning_rate": lr_grid,
        "hgb__max_depth": md_grid,
        "hgb__max_leaf_nodes": mln_grid,
        "hgb__l2_regularization": l2_grid,
    }


def run_search(stage, grid, X, y, cv):
    n = int(np.prod([len(v) for v in grid.values()]))
    print(
        f"\n🔎 Busca {stage.upper()} — {n} combos × {cv.get_n_splits()} folds = {n * cv.get_n_splits()} fits"
    )
    s = GridSearchCV(build_pipeline(), grid, scoring="r2", cv=cv, n_jobs=-1, refit=True)
    t0 = time.time()
    s.fit(X, y)
    print(f"   ⏱️  {time.time() - t0:.1f}s | CV R²={s.best_score_:.5f} | {s.best_params_}")
    return s


def train():
    print(f"🚀 Treino v3 (implantável) — lendo {INPUT_FILE}...")
    df = pd.read_csv(INPUT_FILE)
    df = df[df.category == "Apartamentos"].copy()
    print(f"   {len(df)} apartamentos.")

    df = features.add_engineered(df)
    X = df[features.numeric_features() + ["district"]]
    y = np.log1p(df["price"])

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=RS)
    cv = KFold(n_splits=5, shuffle=True, random_state=RS)

    coarse = run_search("coarse", coarse_grid(), X_tr, y_tr, cv)
    fine = run_search("fine", refine_grid(coarse.best_params_), X_tr, y_tr, cv)
    best = fine if fine.best_score_ >= coarse.best_score_ else coarse
    model = best.best_estimator_

    pred = model.predict(X_te)
    r2 = r2_score(y_te, pred)
    pr, tr = np.expm1(pred), np.expm1(y_te)
    mae = mean_absolute_error(tr, pr)
    mape = float(np.mean(np.abs((tr - pr) / tr)) * 100)

    print("\n" + "=" * 60)
    print(f"📈 R² (v3, holdout) : {r2:.5f}")
    print(f"📈 R² (v3, CV médio): {best.best_score_:.5f}")
    print(f"📈 R² (base antiga) : {BASELINE_A_R2:.5f}")
    print(f"📈 Ganho vs base antiga: {(best.best_score_ - BASELINE_A_R2) * 100:+.2f} pp (CV)")
    print(f"💰 MAE (holdout): R$ {mae:,.2f}  |  📊 MAPE: {mape:.2f}%")
    print("=" * 60)

    os.makedirs(os.path.dirname(OUTPUT_PKL), exist_ok=True)
    metrics = {
        "r2_test": round(float(r2), 5),
        "r2_cv_mean": round(float(best.best_score_), 5),
        "mae_test": round(float(mae), 2),
        "mape_test": round(mape, 2),
        "baseline_base_antiga_cv_r2": BASELINE_A_R2,
    }
    artifact = {
        "model": model,
        "landmarks": features.ALL_LANDMARKS,
        "feature_cols": features.feature_columns(),
        "best_params": best.best_params_,
        "metrics": metrics,
        "version": f"v3_sp2024_apts_r2_{r2:.4f}",
        "notes": "Base Kaggle 2024 (apartamentos). Bairro normalizado dentro do pipeline.",
    }
    joblib.dump(artifact, OUTPUT_PKL)
    print(f"💾 Artefato salvo: {OUTPUT_PKL}  (versão: {artifact['version']})")

    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(
            {
                "coarse": {
                    "params": coarse.best_params_,
                    "cv_r2": round(float(coarse.best_score_), 5),
                },
                "fine": {"params": fine.best_params_, "cv_r2": round(float(fine.best_score_), 5)},
                "metrics": metrics,
                "n_apartamentos": int(len(df)),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"📝 Relatório salvo: {REPORT_JSON}")


if __name__ == "__main__":
    train()
