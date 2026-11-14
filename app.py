"""
app.py
======
インタラクティブ高層気象解析 (Skew-T Log-P) Streamlit Web アプリケーション
（NOAA IGRA v2 実測ゾンデデータ専用・Web公開版）
"""

from datetime import datetime, time
from typing import Optional
import streamlit as st
from meteo_lib import sounding_utils as su
from meteo_lib import sounding_utils_plotly as sup

st.set_page_config(
    page_title="Interactive Skew-T Sounding (IGRA)",
    page_icon="🌤️",
    layout="wide"
)

# -----------------------------------------------------------------------------
# サイドバー設定
# -----------------------------------------------------------------------------
st.sidebar.title("🛠️ Sounding Settings")
st.sidebar.caption("Data Source: NOAA IGRA v2 (Observed Radiosonde)")

# 1. 地点指定（現在も高層ゾンデ観測を継続している国内全14地点）
st.sidebar.subheader("📍 Observation Station")

IGRA_STATIONS = {
    "館野 / つくば (Tateno)": "JAM00047646",
    "札幌 (Sapporo)": "JAM00047412",
    "秋田 (Akita)": "JAM00047582",
    "輪島 (Wajima)": "JAM00047600",
    "潮岬 (Shionomisaki)": "JAM00047778",
    "福岡 (Fukuoka)": "JAM00047807",
    "鹿児島 (Kagoshima)": "JAM00047827",
    "八丈島 (Hachijojima)": "JAM00047678",
    "名瀬 (Naze)": "JAM00047909",
    "那覇 (Naha)": "JAM00047936",
    "石垣島 (Ishigakijima)": "JAM00047918",
    "南大東島 (Minamidaitojima)": "JAM00047945",
    "父島 (Chichijima)": "JAM00047971",
    "南鳥島 (Minamitorishima)": "JAM00047991",
}

selected_station_label = st.sidebar.selectbox(
    "Select Station",
    options=list(IGRA_STATIONS.keys()),
    index=0
)
station_id = IGRA_STATIONS[selected_station_label]
display_location_name = selected_station_label.split(" (")[0]

# 2. 日時指定
st.sidebar.subheader("📅 Date & Time (UTC)")
target_date = st.sidebar.date_input("Date", value=datetime(2026, 10, 11).date())

utc_hour = st.sidebar.radio(
    "Observation Hour (UTC)",
    options=[0, 12],
    format_func=lambda h: f"{h:02d} UTC ({(h + 9) % 24:02d} JST)",
    horizontal=True
)
target_dt = datetime.combine(target_date, time(hour=utc_hour))

# -----------------------------------------------------------------------------
# データロード処理（キャッシュ付与）
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_igra_sounding(dt: datetime, st_id: str):
    """sounding_utils.get_sounding を介してIGRA実測プロファイルを取得"""
    return su.get_sounding(
        source="igra",
        dt=dt,
        station_id=st_id
    )

# -----------------------------------------------------------------------------
# メイン画面描画
# -----------------------------------------------------------------------------
st.title("Interactive Sounding Profile")

st.sidebar.button("🔄 Fetch & Plot", type="primary", use_container_width=True)

title_label = f"{target_dt:%Y-%m-%d %H}UTC {display_location_name} (IGRA)"

with st.spinner(f"Loading IGRA sounding data for {display_location_name}..."):
    try:
        sounding_data = load_igra_sounding(dt=target_dt, st_id=station_id)

        if sounding_data is not None:
            fig = sup.create_skewt_figure(sounding_data, title_info=title_label)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(
                f"指定された日時 ({title_label}) の観測データが見つかりませんでした。"
                "（欠測または未配信の日時の可能性があります）"
            )
    except Exception as e:
        st.error(f"データ取得・描画中にエラーが発生しました: {e}")