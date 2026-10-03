"""Train the optional ML model on synthetic samples and persist it.

Run manually:  python -m app.ml.train
The application NEVER requires this step — predict.py falls back gracefully
to the deterministic estimator when the model file is absent.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

MODEL_PATH = Path(__file__).resolve().parent / "model" / "delay_model.pkl"
META_PATH = Path(__file__).resolve().parent / "model" / "model_meta.json"


def train(n_samples: int = 4000) -> dict:
    import joblib
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split

    from app.ml.features import FEATURE_NAMES
    from app.ml.synthetic import generate_samples

    X, y = generate_samples(n_samples)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=7)

    model = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.08, random_state=7)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": n_samples,
        "r2_test": round(float(r2_score(y_test, preds)), 3),
        "mae_test_minutes": round(float(mean_absolute_error(y_test, preds)), 3),
        "feature_names": FEATURE_NAMES,
        "data_label": "Prototype / synthetic training data (noisy rule-estimator labels)",
    }
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


if __name__ == "__main__":
    print(json.dumps(train(), indent=2))
