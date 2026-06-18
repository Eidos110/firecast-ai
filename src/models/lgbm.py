import os
import joblib
from src import config


def load_lgbm_model(model_path: str = None):
    """Muat model LightGBM dari file.

    Args:
        model_path: Optional path ke model. Jika None, gunakan path default dari config.

    Mendukung kedua format: joblib dan native LightGBM txt model.
    """
    if model_path is None:
        model_path = config.LGBM_MODEL_PATH

    # Coba load dengan joblib dulu (format lama)
    try:
        model = joblib.load(model_path)
        # Verifikasi model valid dengan mencoba akses atribut dasar
        if hasattr(model, "predict"):
            return model
    except Exception:
        pass

    # Jika gagal, coba load dengan native LightGBM
    try:
        import lightgbm as lgb

        # Cek jika file txt model exists
        txt_path = str(model_path).replace(".pkl", ".txt")
        if os.path.exists(txt_path):
            model = lgb.Booster(model_file=txt_path)
            return model
    except Exception:
        pass

    # Fallback: load dan re-inisialisasi jika perlu
    try:
        import lightgbm as lgb

        model = joblib.load(model_path)
        # Jika model adalah dictionary (booster params), buat ulang
        if isinstance(model, dict) and "booster" in model:
            booster = lgb.Booster(model_str=model["booster"])
            return booster
        return model
    except Exception as e:
        raise RuntimeError(f"Gagal memuat model LightGBM: {e}")
