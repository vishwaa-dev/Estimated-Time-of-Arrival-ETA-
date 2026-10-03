"""Lazy ML inference with graceful fallback.

Returns None whenever the model is unavailable (not trained, sklearn missing,
or feature mismatch) — the prediction engine then uses the deterministic
rule-based estimator. The application never breaks because of ML.
"""
from app.ml.features import FEATURE_NAMES

_model = None
_loaded = False


def _load():
    global _model, _loaded
    if _loaded:
        return _model
    _loaded = True
    try:
        import joblib

        from app.ml.train import MODEL_PATH
        if not MODEL_PATH.exists():
            return None
        _model = joblib.load(MODEL_PATH)
    except Exception:
        _model = None
    return _model


def predict_additional(vector: list[float]) -> float | None:
    model = _load()
    if model is None:
        return None
    try:
        return max(0.0, min(60.0, float(model.predict([vector])[0])))
    except Exception:
        return None
