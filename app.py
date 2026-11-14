"""
app.py
======
インタラクティブ高層気象解析 (Skew-T Log-P) Streamlit Web アプリケーション
"""

from datetime import datetime, time
from typing import Optional
import streamlit as st
from meteo_lib import sounding_utils as su
from meteo_lib import sounding_utils_plotly as sup

st.set_page_config(
    page_title="Interactive Skew-T Sounding",
    page_icon="🌤️",
    layout="wide"
)

# -----------------------------------------------------------------------------
# サイドバー設定
# -----------------------------------------------------------------------------
st.sidebar.title("🛠️ Sounding Settings")

# 1. データソース選択（ERA5を削除し、MSMとIGRAのみに整理）
data_source = st.sidebar.selectbox(
    "Data Source",
    options=["MSM", "IGRA (Observed)"],
    index=1
)
is_igra = data_source.startswith("IGRA")

# 2. 地点指定
st.sidebar.subheader("📍 Location")

# 代表地点プリセット（igra_active: 現在も高層ゾンデ観測を継続している地点か）
PRESET_CITIES = {
    "館野/つくば (Tateno)": {"lat": 36.0583, "lon": 140.1250, "igra_id": "JAM00047646", "igra_active": True},
    "仙台 (Sendai)": {"lat": 38.2682, "lon": 140.8694, "igra_id": "JAM00047590", "igra_active": False},
    "秋田 (Akita)": {"lat": 39.7167, "lon": 140.1000, "igra_id": "JAM00047582", "igra_active": True},
    "輪島 (Wajima)": {"lat": 37.3833, "lon": 136.9000, "igra_id": "JAM00047600", "igra_active": True},
    "札幌 (Sapporo)": {"lat": 43.0642, "lon": 141.3469, "igra_id": "JAM00047412", "igra_active": True},
    "八丈島 (Hachijojima)": {"lat": 33.1167, "lon": 139.7833, "igra_id": "JAM00047678", "igra_active": True},
    "鹿児島 (Kagoshima)": {"lat": 31.5597, "lon": 130.5571, "igra_id": "JAM00047827", "igra_active": True},
}

# IGRA選択時は観測地点のみ、MSM選択時は任意の緯度経度指定も許可
if is_igra:
    loc_mode = "Preset City"
else:
    loc_mode = st.sidebar.radio("Location Mode", ["Preset City", "Latitude / Longitude"], horizontal=True)

if loc_mode == "Preset City":
    # IGRA選択時は観測終了地点（仙台）を除外
    available_cities = {
        k: v for k, v in PRESET_CITIES.items()
        if (not is_igra) or v["igra_active"]
    }
    selected_city_name = st.sidebar.selectbox(
        "Select Station / City",
        list(available_cities.keys()),
        index=0
    )
    city_info = available_cities[selected_city_name]
    lat = city_info["lat"]
    lon = city_info["lon"]
    display_location_name = selected_city_name.split(" ")[0]
else:
    col_lat, col_lon = st.sidebar.columns(2)
    lat = col_lat.number_input("Latitude (°N)", value=38.2682, min_value=-90.0, max_value=90.0, step=0.1)
    lon = col_lon.number_input("Longitude (°E)", value=140.8694, min_value=-180.0, max_value=180.0, step=0.1)
    display_location_name = f"Lat: {lat:.2f}, Lon: {lon:.2f}"

# 3. 日時指定
st.sidebar.subheader("📅 Date & Time (UTC)")
target_date = st.sidebar.date_input("Date", value=datetime(2026, 10, 11).date())

# IGRAは00/12UTCのみ、MSMは3時間ごと
hour_options = [0, 12] if is_igra else [0, 3, 6, 9, 12, 15, 18, 21]
utc_hour = st.sidebar.select_slider(
    "Hour (UTC)",
    options=hour_options,
    value=0
)
target_dt = datetime.combine(target_date, time(hour=utc_hour))

# -----------------------------------------------------------------------------
# データロード処理（キャッシュ付与）
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_sounding_data(
    source_name: str,
    dt: datetime,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    station: Optional[str] = None
):
    """sounding_utils.get_sounding を介してプロファイル辞書を取得"""
    src_key = source_name.lower().split()[0]  # "IGRA (Observed)" -> "igra"
    return su.get_sounding(
        source=src_key,
        dt=dt,
        lat=lat,
        lon=lon,
        station=station
    )

# -----------------------------------------------------------------------------
# メイン画面描画
# -----------------------------------------------------------------------------
st.title("Interactive Sounding Profile")

run_button = st.sidebar.button("🔄 Fetch & Plot", type="primary", use_container_width=True)

title_label = f"{target_dt:%Y-%m-%d %H}UTC {display_location_name} ({data_source.split(' ')[0]})"

with st.spinner(f"Loading sounding data from {data_source}..."):
    try:
        sounding_data = load_sounding_data(
            source_name=data_source,
            dt=target_dt,
            lat=lat,
            lon=lon,
            station=display_location_name if loc_mode == "Preset City" else None
        )

        if sounding_data is not None:
            fig = sup.create_skewt_figure(sounding_data, title_info=title_label)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(f"指定された条件 ({title_label}) のデータが見つかりませんでした。")
    except Exception as e:
        st.error(f"データ取得・描画中にエラーが発生しました: {e}")