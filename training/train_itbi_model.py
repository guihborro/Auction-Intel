"""
train_itbi_model.py — Piso de valor a partir do ITBI (preço REAL pago), tier cadastral.

Por que ITBI: o comparativo mostrou que treinar com preço de ANÚNCIO (Kaggle)
super-representa imóveis premium (viés de seleção) → superestima o valor de
imóveis comuns/periféricos, justamente os típicos de leilão. O ITBI traz TODAS
as transações de apartamento da cidade em 2024 (~67k), com o valor REALMENTE
transacionado — base bem mais representativa e calibrada.

Diferença de schema: o ITBI NÃO tem quartos/banheiros/vagas. Usamos as features
que ele tem: área construída, área do terreno, fração ideal, idade do imóvel,
padrão construtivo (IPTU) e bairro + geo (distâncias de landmarks).

Geo: como o ITBI tem 67k endereços (geocoding preciso em massa é inviável no
Nominatim público), esta 1ª versão usa CENTROIDE de bairro derivado da base
atual — offline. Geo precisa (via SQL cadastral/GeoSampa) fica como upgrade.

Target: Valor de Transação declarado (col 8), que em 75% dos casos está acima do
Valor Venal de Referência (não há subdeclaração sistemática). y = log1p(price).

Salva em models/itbi_model.pkl.
Rodar da raiz do repositório: python training/train_itbi_model.py
"""

import json
import os
import re
import time
import unicodedata

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GridSearchCV, KFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, TargetEncoder

from auction_intel.features import engineering as features

ITBI_FILE = "datasets/itbi_2024_apartments.csv"
COORDS_FILE = "datasets/quadra_coords.csv"
OUTPUT_PKL = "models/itbi_model.pkl"
REPORT_JSON = "models/itbi_model_report.json"
ANO_BASE = 2024
RS = 42

NUM_FEATURES = [
    "area",
    "log_area",
    "area_terreno",
    "fracao_ideal",
    "idade",
    "latitude",
    "longitude",
] + list(features.ALL_LANDMARKS.keys())
# Localização categórica: setor fiscal (385 zonas limpas) — o "bairro" do ITBI é
# inutilizável (34% vazio, resto com 'torre/bloco'). Padrão construtivo do IPTU.
CAT_FEATURES = ["setor", "padrao"]


def norm_district(s):
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def prepare():
    df = pd.read_csv(ITBI_FILE)
    print(f"   {len(df)} apartamentos ITBI carregados.")

    # Idade do imóvel
    df["idade"] = (ANO_BASE - pd.to_numeric(df["ano_constr"], errors="coerce")).clip(0, 150)
    df["idade"] = df["idade"].fillna(df["idade"].median())
    df["area_terreno"] = pd.to_numeric(df["area_terreno"], errors="coerce").fillna(0)
    df["fracao_ideal"] = pd.to_numeric(df["fracao_ideal"], errors="coerce").fillna(1.0)
    df["padrao"] = df["padrao"].astype(str).fillna("desconhecido")

    # Geo por QUADRA (GeoSampa/SQL) + setor fiscal como zona categórica.
    # SQL canônico = 11 dígitos (SSS.QQQ.LLLL-D); quadra = setor+quadra (6 díg.).
    df["sql11"] = df["sql"].astype("Int64").astype(str).str.zfill(11)
    df["setor"] = df["sql11"].str[:3]
    df["quadra6"] = df["sql11"].str[:6]
    coords = pd.read_csv(COORDS_FILE, dtype={"quadra6": str}).drop_duplicates("quadra6")[
        ["quadra6", "latitude", "longitude"]
    ]
    df = df.merge(coords, on="quadra6", how="left")
    antes = len(df)
    df = df.dropna(subset=["latitude", "longitude"])
    print(f"   {len(df)}/{antes} com coordenada por quadra ({100 * len(df) / antes:.1f}%).")

    df = features.add_engineered(df)  # log_area + distâncias
    X = df[NUM_FEATURES + CAT_FEATURES]
    y = np.log1p(df["price"])
    return X, y, len(df)


def build_pipeline():
    pre = ColumnTransformer(
        [
            ("cat", TargetEncoder(target_type="continuous", random_state=RS), CAT_FEATURES),
            ("num", StandardScaler(), NUM_FEATURES),
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


def refine_grid(b):
    lr, md, mln, l2 = (
        b["hgb__learning_rate"],
        b["hgb__max_depth"],
        b["hgb__max_leaf_nodes"],
        b["hgb__l2_regularization"],
    )
    lr_g = sorted({round(max(0.005, lr * f), 4) for f in (0.6, 1.0, 1.5)})
    mln_g = sorted({max(15, int(mln * f)) for f in (0.75, 1.0, 1.5)})
    md_g = [None, 10, 16] if md is None else sorted({max(2, md - 3), md, md + 4})
    l2_g = sorted({0.0, l2, round(l2 + 0.5, 2)}) if l2 > 0 else [0.0, 0.5, 1.0]
    return {
        "hgb__learning_rate": lr_g,
        "hgb__max_depth": md_g,
        "hgb__max_leaf_nodes": mln_g,
        "hgb__l2_regularization": l2_g,
    }


def run_search(stage, grid, X, y, cv):
    n = int(np.prod([len(v) for v in grid.values()]))
    print(
        f"\n🔎 {stage.upper()} — {n} combos × {cv.get_n_splits()} folds = {n * cv.get_n_splits()} fits"
    )
    s = GridSearchCV(build_pipeline(), grid, scoring="r2", cv=cv, n_jobs=-1)
    t0 = time.time()
    s.fit(X, y)
    print(f"   ⏱️  {time.time() - t0:.0f}s | CV R²={s.best_score_:.5f} | {s.best_params_}")
    return s


def main():
    print(f"🚀 Treino ITBI — {ITBI_FILE}")
    X, y, n = prepare()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=RS)
    cv = KFold(5, shuffle=True, random_state=RS)

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
    print(f"📈 R² (ITBI, holdout) : {r2:.5f}")
    print(f"📈 R² (ITBI, CV médio): {best.best_score_:.5f}")
    print(f"💰 MAE: R$ {mae:,.0f} | 📊 MAPE: {mape:.2f}%")
    print(f"ℹ️  Preço mediano real (ITBI): R$ {np.expm1(y).median():,.0f}")
    print("=" * 60)

    os.makedirs(os.path.dirname(OUTPUT_PKL), exist_ok=True)
    metrics = {
        "r2_test": round(float(r2), 5),
        "r2_cv_mean": round(float(best.best_score_), 5),
        "mae_test": round(float(mae), 2),
        "mape_test": round(mape, 2),
        "n": int(n),
    }
    joblib.dump(
        {
            "model": model,
            "landmarks": features.ALL_LANDMARKS,
            "num_features": NUM_FEATURES,
            "cat_features": CAT_FEATURES,
            "best_params": best.best_params_,
            "metrics": metrics,
            "version": f"itbi2024_apts_r2_{r2:.4f}",
            "notes": "ITBI 2024 (preço transacionado). Sem quartos/banheiros. Geo EXATA por lote (GeoSampa/SQL).",
        },
        OUTPUT_PKL,
    )
    print(f"💾 Salvo: {OUTPUT_PKL}")
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(
            {
                "coarse": {
                    "params": coarse.best_params_,
                    "cv_r2": round(float(coarse.best_score_), 5),
                },
                "fine": {"params": fine.best_params_, "cv_r2": round(float(fine.best_score_), 5)},
                "metrics": metrics,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"📝 Relatório: {REPORT_JSON}")


if __name__ == "__main__":
    main()
