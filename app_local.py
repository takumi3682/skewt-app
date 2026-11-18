"""
app_local.py
============
ローカル環境専用 インタラクティブ高層気象解析 (Skew-T Log-P / エマグラム)
対応ソース:
  - IGRA / JMA 実測ゾンデ
  - JMA MSM 初期値 (2006〜)
  - ERA5 再解析データ
"""

from datetime import datetime, timedelta, timezone
import inspect
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import streamlit as st
import io
import re

# 日本語フォント対応（グラフタイトルの地点名文字化け防止）
try:
    import japanize_matplotlib  # noqa: F401
except ImportError:
    plt.rcParams["font.sans-serif"] = [
        "Hiragino Sans",
        "Yu Gothic",
        "Meiryo",
        "Noto Sans CJK JP",
        "sans-serif",
    ]

from meteo_lib import sounding_utils as su
from meteo_lib import sounding_utils_plotly as sup

st.set_page_config(
    page_title="Interactive Skew-T Viewer (IGRA / MSM / ERA5)",
    page_icon="🌤️",
    layout="wide",
)

# -----------------------------------------------------------------------------
# 定数・初期値設定
# -----------------------------------------------------------------------------
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


def get_default_utc_dt(source: str) -> datetime:
    """データソースに応じたデフォルトのUTC日時を返す"""
    jst = timezone(timedelta(hours=9))
    now_utc = datetime.now(jst).astimezone(timezone.utc)

    if source == "igra":
        avail = now_utc - timedelta(hours=26)
        hour = 12 if avail.hour >= 12 else 0
        return datetime(avail.year, avail.month, avail.day, hour)
    elif source == "msm":
        avail = now_utc - timedelta(hours=6)
        hour = (avail.hour // 3) * 3
        return datetime(avail.year, avail.month, avail.day, hour)
    else:
        avail = now_utc - timedelta(days=6)
        return datetime(avail.year, avail.month, avail.day, 0)


def customize_mpl_layout(fig: plt.Figure) -> None:
    """
    Matplotlib描画後のレイアウト調整:
      1. 左下にある安定度指数ボックス(CAPE/CIN等)を右上へ移動
      2. LCL / LFC / EL の水平線近傍（左端）にラベルを表示
    """
    if not fig.axes:
        return
    ax = fig.axes[0]

    # 1. 安定度指数ボックス（左下）を右上へ移動
    for txt in ax.texts:
        content = txt.get_text()
        x_pos, y_pos = txt.get_position()
        if any(k in content for k in ("CAPE", "CIN", "PWAT", "SSI")) or (
            x_pos < 0.35 and y_pos < 0.35
        ):
            txt.set_position((0.98, 0.98))
            txt.set_ha("right")
            txt.set_va("top")

    # 2. 水平線（LCL / LFC / EL）の左端近傍にラベルを描画
    existing_texts = {t.get_text().strip() for t in ax.texts}
    y_trans = ax.get_yaxis_transform()  # Xは軸比率(0〜1)、Yは気圧(hPa)の座標系

    for line in ax.lines:
        label = line.get_label()
        if not label or label.startswith("_"):
            continue
        if any(key in label for key in ("LCL", "LFC", "EL")):
            ydata = line.get_ydata()
            if len(ydata) > 0 and label not in existing_texts:
                # Pintの単位(hectopascal)を保持したまま渡す
                y_val = ydata[0]
                ax.text(
                    0.015,
                    y_val,
                    label,
                    transform=y_trans,
                    color=line.get_color(),
                    fontsize=8,
                    va="bottom",
                    ha="left",
                    bbox=dict(
                        boxstyle="round,pad=0.12",
                        facecolor="white",
                        edgecolor="none",
                        alpha=0.75,
                    ),
                )


# -----------------------------------------------------------------------------
# サイドバー設定
# -----------------------------------------------------------------------------
st.sidebar.title("🛠️ Sounding Settings")

# 1. データソース選択
st.sidebar.subheader("🗄️ Data Source")
source_label = st.sidebar.radio(
    "Select Data Source",
    options=["IGRA / JMA (実測)", "MSM (気象庁初期値)", "ERA5 (再解析)"],
    index=0,
)

if source_label.startswith("IGRA"):
    source_key = "igra"
elif source_label.startswith("MSM"):
    source_key = "msm"
else:
    source_key = "era5"

# 2. 地点・座標指定
st.sidebar.subheader("📍 Location")

station_name = None
station_id = None
lat = None
lon = None

if source_key == "igra":
    selected_station_label = st.sidebar.selectbox(
        "Observation Station",
        options=list(IGRA_STATIONS.keys()),
        index=0,
    )
    station_id = IGRA_STATIONS[selected_station_label]
    station_name = selected_station_label.split(" (")[0]
    display_location_name = station_name
else:
    loc_mode = st.sidebar.radio(
        "Location Input Mode",
        options=["地点名で指定", "緯度・経度で指定"],
        horizontal=True,
    )
    if loc_mode == "地点名で指定":
        station_name = st.sidebar.text_input(
            "地点名（例: 仙台, 古川, 名古屋, 東京）",
            value="仙台",
        ).strip()
        display_location_name = station_name
    else:
        col_lat, col_lon = st.sidebar.columns(2)
        with col_lat:
            lat = st.number_input(
                "緯度 (Lat)", min_value=-90.0, max_value=90.0, value=38.26, step=0.05, format="%.3f"
            )
        with col_lon:
            lon = st.number_input(
                "経度 (Lon)", min_value=-180.0, max_value=180.0, value=140.90, step=0.05, format="%.3f"
            )
        display_location_name = f"{lat:.2f}N, {lon:.2f}E"

# 3. 日時指定 (UTC)
st.sidebar.subheader("📅 Date & Time (UTC)")
default_dt = get_default_utc_dt(source_key)
jst_today = datetime.now(timezone(timedelta(hours=9))).date()

min_date = (
    datetime(1940, 1, 1).date()
    if source_key == "era5"
    else (datetime(2006, 1, 1).date() if source_key == "msm" else datetime(1950, 1, 1).date())
)

selected_date = st.sidebar.date_input(
    "Date (UTC)",
    value=default_dt.date(),
    min_value=min_date,
    max_value=jst_today,
)

if source_key == "igra":
    utc_options = [0, 12]
elif source_key == "msm":
    utc_options = [0, 3, 6, 9, 12, 15, 18, 21]
else:
    utc_options = list(range(24))

default_hour = default_dt.hour if default_dt.hour in utc_options else utc_options[0]

selected_hour = st.sidebar.select_slider(
    "Hour (UTC)",
    options=utc_options,
    value=default_hour,
    format_func=lambda h: f"{h:02d}UTC ({(h + 9) % 24:02d}JST)",
)

target_dt = datetime(
    selected_date.year, selected_date.month, selected_date.day, selected_hour
)

# 4. 描画設定
st.sidebar.subheader("📐 Diagram Settings")
rotation = st.sidebar.radio(
    "Isotherm Skew Angle",
    options=[0, 45],
    format_func=lambda deg: "0° (日本式エマグラム)" if deg == 0 else "45° (Skew-T Log-P)",
    index=0,
    horizontal=True,
)

render_engine = st.sidebar.radio(
    "Plot Engine",
    options=["Plotly (インタラクティブ)", "Matplotlib (静的画像 / qmd互換)"],
    index=0,
)

# -----------------------------------------------------------------------------
# データ取得処理（キャッシュ付与）
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def load_sounding_data(
    source: str,
    dt: datetime,
    station: str | None = None,
    station_id: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
):
    """
    sounding_utils.get_sounding を呼び出すラッパー。
    緯度経度指定時の引数名（lat/lon または coords 等）を自動判別して渡す。
    """
    sig = inspect.signature(su.get_sounding)
    params = sig.parameters

    kwargs = {"source": source, "dt": dt}

    if source == "igra":
        if "station_id" in params and station_id:
            kwargs["station_id"] = station_id
        elif "station" in params and station:
            kwargs["station"] = station
    else:
        if lat is not None and lon is not None:
            if "lat" in params and "lon" in params:
                kwargs["lat"] = lat
                kwargs["lon"] = lon
            elif "latitude" in params and "longitude" in params:
                kwargs["latitude"] = lat
                kwargs["longitude"] = lon
            elif "coords" in params:
                kwargs["coords"] = (lat, lon)
            else:
                kwargs["lat"] = lat
                kwargs["lon"] = lon
        elif station:
            kwargs["station"] = station

    return su.get_sounding(**kwargs)


# -----------------------------------------------------------------------------
# メイン画面描画
# -----------------------------------------------------------------------------
st.title("Interactive Sounding Profile")
st.sidebar.button("🔄 Fetch & Plot", type="primary", use_container_width=True)

with st.spinner(f"Loading {source_key.upper()} sounding data for {display_location_name}..."):
    try:
        plot_dt = target_dt
        sounding_data = load_sounding_data(
            source=source_key,
            dt=plot_dt,
            station=station_name,
            station_id=station_id,
            lat=lat,
            lon=lon,
        )

        # IGRAデフォルト日時が未配信だった場合のみ自動遡及
        if sounding_data is None and source_key == "igra" and target_dt == default_dt:
            for back_hours in (12, 24, 36):
                cand_dt = target_dt - timedelta(hours=back_hours)
                sounding_data = load_sounding_data(
                    source=source_key,
                    dt=cand_dt,
                    station=station_name,
                    station_id=station_id,
                )
                if sounding_data is not None:
                    plot_dt = cand_dt
                    break

        if sounding_data is not None:
            default_origin = {"igra": "IGRA", "msm": "JMA MSM", "era5": "ERA5"}[source_key]
            origin = (
                sounding_data.get("data_origin", default_origin)
                if isinstance(sounding_data, dict)
                else default_origin
            )
            title_label = f"{plot_dt:%Y-%m-%d %H}UTC {display_location_name} ({origin})"

            if render_engine.startswith("Plotly"):
                fig = sup.create_skewt_figure(
                    sounding_data,
                    title_info=title_label,
                    rotation=rotation,
                )
                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    config={"toImageButtonOptions": {"format": "png", "scale": 3}},
                )

            else:
                plt.close("all")
                ret = su.plot_sounding(
                    sounding_data,
                    title_info=title_label,
                    rotation=rotation,
                )
                fig_mpl = ret[0] if isinstance(ret, tuple) else (ret or plt.gcf())
                customize_mpl_layout(fig_mpl)
                st.pyplot(fig_mpl, use_container_width=False)

                # SVGバッファへ書き出し（余白を自動調整）
                svg_buf = io.BytesIO()
                fig_mpl.savefig(svg_buf, format="svg", bbox_inches="tight")
                svg_bytes = svg_buf.getvalue()

                # 保存ファイル名の生成（例: SkewT_20261031_09UTC_仙台_MSM_skew0.svg）
                safe_loc = re.sub(r'[\\/:*?"<>|,\s]+', "_", display_location_name).strip("_")
                safe_orig = re.sub(r'[\\/:*?"<>|,\s]+', "_", origin).strip("_")
                svg_filename = (
                    f"SkewT_{plot_dt:%Y%m%d_%HUTC}_{safe_loc}_{safe_orig}_skew{rotation}.svg"
                )

                st.download_button(
                    label="💾 SVGファイルをダウンロード",
                    data=svg_bytes,
                    file_name=svg_filename,
                    mime="image/svg+xml",
                )
        else:
            st.warning(
                f"指定された条件 ({target_dt:%Y-%m-%d %H}UTC / {display_location_name} / {source_key.upper()}) "
                "のデータが見つかりませんでした。（欠測・未配信・範囲外の可能性があります）"
            )
    except Exception as e:
        st.error(f"データ取得・描画中にエラーが発生しました: {e}")