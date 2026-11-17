"""
app.py
======
インタラクティブ高層気象解析 (Skew-T Log-P / エマグラム) Streamlit Web アプリケーション
（NOAA IGRA v2 / 気象庁 JMA 実測ゾンデデータ対応）
"""

from datetime import datetime, timedelta, timezone
import streamlit as st
from meteo_lib import sounding_utils as su
from meteo_lib import sounding_utils_plotly as sup

st.set_page_config(
    page_title="Interactive Skew-T Sounding (JMA / IGRA)",
    page_icon="🌤️",
    layout="wide"
)


def get_latest_jma_sounding_dt() -> datetime:
    """現在時刻から確実に公開済みの最新JMA高層観測日時（UTC）を算出する（更新遅延26時間を考慮）"""
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    avail_jst = now_jst - timedelta(hours=26)

    if avail_jst.hour >= 21:
        return datetime(avail_jst.year, avail_jst.month, avail_jst.day, 12)
    elif avail_jst.hour >= 9:
        return datetime(avail_jst.year, avail_jst.month, avail_jst.day, 0)
    else:
        prev_day = avail_jst - timedelta(days=1)
        return datetime(prev_day.year, prev_day.month, prev_day.day, 12)


# -----------------------------------------------------------------------------
# サイドバー設定
# -----------------------------------------------------------------------------
st.sidebar.title("🛠️ Sounding Settings")
st.sidebar.caption("Data Source: NOAA IGRA v2 / JMA Observed Radiosonde")

# 1. 地点指定（現在も高層ゾンデ観測を継続している国内全14地点）
st.sidebar.subheader("📍 Observation Station")

IGRA_STATIONS = {
    "秋田 (Akita)": "JAM00047582",
    "札幌 (Sapporo)": "JAM00047412",
    "館野 / つくば (Tateno)": "JAM00047646",
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
st.sidebar.subheader("📅 Observation Date & Time (UTC)")

default_dt = get_latest_jma_sounding_dt()
jst_today = datetime.now(timezone(timedelta(hours=9))).date()

selected_date = st.sidebar.date_input(
    "Date (UTC)",
    value=default_dt.date(),
    max_value=jst_today,
)

utc_options = [0, 12]
default_hour_index = utc_options.index(default_dt.hour)

selected_hour = st.sidebar.selectbox(
    "Hour (UTC)",
    options=utc_options,
    index=default_hour_index,
    format_func=lambda h: f"{h:02d}:00 UTC ({(h + 9) % 24:02d}:00 JST)",
)

target_dt = datetime(
    selected_date.year, selected_date.month, selected_date.day, selected_hour
)

# 3. 描画モード（等温線の傾斜角）の切り替え
st.sidebar.subheader("📐 Diagram Mode")
rotation = st.sidebar.radio(
    "Isotherm Skew Angle",
    options=[0, 45],
    format_func=lambda deg: "0° (日本式エマグラム)" if deg == 0 else "45° (Skew-T Log-P)",
    index=0,
    horizontal=True
)

# -----------------------------------------------------------------------------
# データロード処理（キャッシュ付与: 1時間で自動更新）
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def load_igra_sounding(dt: datetime, st_id: str):
    """sounding_utils.get_sounding を介して実測プロファイル（JMA/IGRA）を取得"""
    return su.get_sounding(
        source="igra",
        dt=dt,
        station_id=st_id
    )


# -----------------------------------------------------------------------------
# メイン画面描画
# -----------------------------------------------------------------------------
st.title("Interactive Sounding Profile")

st.sidebar.button("🔄 Fetch & Plot", type="primary", width="stretch")

with st.spinner(f"Loading sounding data for {display_location_name}..."):
    try:
        plot_dt = target_dt
        sounding_data = load_igra_sounding(dt=plot_dt, st_id=station_id)

        # デフォルト日時が未配信だった場合は最大36時間前まで12時間刻みで自動遡及
        if sounding_data is None and target_dt == default_dt:
            for back_hours in (12, 24, 36):
                cand_dt = target_dt - timedelta(hours=back_hours)
                sounding_data = load_igra_sounding(dt=cand_dt, st_id=station_id)
                if sounding_data is not None:
                    plot_dt = cand_dt
                    break

        if sounding_data is not None:
            origin = sounding_data.get("data_origin", "IGRA")
            title_label = f"{plot_dt:%Y-%m-%d %H}UTC {display_location_name} ({origin})"
            fig = sup.create_skewt_figure(
                sounding_data,
                title_info=title_label,
                rotation=rotation,
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.warning(
                f"指定された日時 ({target_dt:%Y-%m-%d %H}UTC {display_location_name}) の観測データが見つかりませんでした。"
                "（欠測または未配信の日時の可能性があります）"
            )
    except Exception as e:
        st.error(f"データ取得・描画中にエラーが発生しました: {e}")