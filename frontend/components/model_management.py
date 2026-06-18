"""
Model Management Component
Displays model versions, allows activation, and shows performance metrics.
"""

import streamlit as st
from sqlalchemy import select
from src.models import registry
from src.database import get_engine, Session, ModelVersion


def render_model_management():
    """Render model management UI."""
    st.markdown("### 🧰 Model Management")
    st.markdown("Kelola dan pilih model prediksi.")

    st.markdown("---")
    st.markdown("#### 🤖 Pilih Model Prediksi")

    col1, col2 = st.columns([2, 1])
    with col1:
        current_model = st.session_state.get("active_model_type", "new")
        model_options = [
            ("new", "Model Stacking"),
            ("legacy", "Model Ensemble"),
        ]
        selected_model = st.selectbox(
            "Model yang digunakan",
            options=model_options,
            format_func=lambda x: x[1],
            index=0 if current_model == "new" else 1,
            key="model_type_selector",
            help="Pilih model yang akan digunakan untuk prediksi",
        )
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if selected_model[0] == "new":
            st.success("🤖 Model Stacking")
        else:
            st.info("🔧 Model Ensemble")

    if (
        "active_model_type" not in st.session_state
        or st.session_state.get("active_model_type") != selected_model[0]
    ):
        st.session_state["active_model_type"] = selected_model[0]

    st.markdown("---")

    db = get_engine()
    if db is None:
        st.warning(
            "Database tidak tersedia - menampilkan informasi model dari file lokal"
        )
        _render_local_model_info()
        return

    with Session(db) as session:
        # Get distinct model names
        stmt = select(ModelVersion.model_name).distinct()
        results = session.execute(stmt).all()
        model_names = [r[0] for r in results]

        if not model_names:
            st.info("Belum ada model yang terdaftar di database.")
            _render_local_model_info()
            return

        for model_name in model_names:
            st.markdown(f"**{model_name.upper()} Models**")
            versions = registry.get_model_versions(model_name)
            active_version = registry.get_active_model_version(model_name)

            # Display versions in a tabbed view or accordion
            for version in versions:
                is_active = version.is_active
                metadata = version.metadata or {}
                perf = version.performance_metrics or {}

                with st.expander(
                    f"Version: {version.version_string} | {'✅ Active' if is_active else '⏸️ Inactive'}"
                ):
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.markdown(f"**File:** `{version.file_path}`")
                        if metadata:
                            st.markdown(f"*{metadata.get('description', '')}*")
                        if perf:
                            st.metric(
                                "Accuracy", f"{perf.get('accuracy', 0) * 100:.1f}%"
                            )
                            st.metric(
                                "Precision", f"{perf.get('precision', 0) * 100:.1f}%"
                            )
                            st.metric("Recall", f"{perf.get('recall', 0) * 100:.1f}%")
                    with col2:
                        if not is_active:
                            if st.button(
                                f"Aktifkan",
                                key=f"activate_{model_name}_{version.version_string}",
                            ):
                                if registry.activate_model_version(
                                    model_name, version.version_string
                                ):
                                    st.success("✅ Version diaktifkan!")
                                else:
                                    st.error("Gagal mengaktifkan versi")
                    st.markdown("---")

            st.markdown("")


def _render_local_model_info():
    """Render local model file information when database is not available."""
    import os
    from pathlib import Path

    st.markdown("#### 📁 File Model Lokal")

    base_dir = Path(__file__).parent.parent.parent
    models_dir = base_dir / "models"
    new_models_dir = base_dir / "add_new_model"

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Model Ensemble**")
        if models_dir.exists():
            for f in models_dir.glob("*"):
                if f.suffix in [".pkl", ".pth", ".json"]:
                    st.markdown(f"- `{f.name}`")
        else:
            st.markdown("- Folder tidak ditemukan")

    with col2:
        st.markdown("**Model Stacking**")
        if new_models_dir.exists():
            for f in new_models_dir.glob("*"):
                if f.suffix in [".pkl", ".pth", ".json"]:
                    st.markdown(f"- `{f.name}`")
        else:
            st.markdown("- Folder tidak ditemukan")

    # Add new model version button
    st.markdown("### 📝 Daftar Versi Model Baru")
    col_model, col_version, col_path = st.columns(3)
    with col_model:
        model_name = st.selectbox("Nama Model", ["cnn", "lgbm", "xgb", "bigru"])
    with col_version:
        version = st.text_input("Versi Model (contoh: v2.0.0)", value="v1.0.0")
    with col_path:
        file_path = st.text_input(
            "Path File Model", placeholder="contoh: /path/to/model.pkl"
        )

    if st.button("Daftarkan Model", type="primary", use_container_width=True):
        if not file_path or not model_name or not version:
            st.error("Mohon isi semua field")
        else:
            success = registry.register_model_version(
                model_name=model_name,
                version=version,
                file_path=file_path,
                performance_metrics={
                    "accuracy": 0.95,
                    "precision": 0.96,
                    "recall": 0.94,
                },
            )
            if success:
                st.success(
                    f"✅ Model {model_name} versi {version} berhasil didaftarkan!"
                )
            else:
                st.error("Gagal mendaftarkan model")
