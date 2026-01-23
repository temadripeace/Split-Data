import streamlit as st
import pandas as pd
import geopandas as gpd
import re
import zipfile
import tempfile
import os
from io import BytesIO
from shapely import wkt
from shapely.errors import WKTReadingError

# ---------------- Page Config ----------------
st.set_page_config(
    page_title="Grouped Data Splitting Tool",
    layout="centered"
)

# ---------------- Header ----------------
col1, col2, col3 = st.columns([1, 3, 1])
with col2:
    st.image("Sucafina Logo.jpg", width=500)

st.markdown("<h3 style='text-align:center;'>Grouped Data Splitting Tool</h3>", unsafe_allow_html=True)

st.markdown(
    """
    <div style="text-align: justify; font-size: 16px;">
        Split tabular or spatial data by one or two user-selected columns.
        Output files always reflect the deepest split level.
        Supported formats: <b>CSV</b>, <b>Excel</b>, <b>GeoJSON</b>, <b>KML</b>.
    </div>
    """,
    unsafe_allow_html=True
)

# ---------------- Helpers ----------------
def safe_name(value):
    name = re.sub(r'[<>:"/\\|?*{}]+', "_", str(value)).strip("_")
    return name if name else "UNKNOWN"


def convert_to_geodf(df):
    wkt_columns = [
        col for col in df.columns
        if col.lower() in {
            "gps_point", "gps_polygon", "plot_gps_point",
            "plot_gps_polygon", "plot_wkt", "wkt", "geometry"
        }
    ]

    for col in wkt_columns:
        try:
            geom = df[col].apply(
                lambda x: wkt.loads(str(x))
                if pd.notnull(x) and str(x).strip() != ""
                else None
            )
            if geom.notnull().any():
                return gpd.GeoDataFrame(df.copy(), geometry=geom, crs="EPSG:4326")
        except (WKTReadingError, Exception):
            pass

    lon_cols = [c for c in df.columns if "lon" in c.lower()]
    lat_cols = [c for c in df.columns if "lat" in c.lower()]

    if lon_cols and lat_cols:
        try:
            geom = gpd.points_from_xy(df[lon_cols[0]], df[lat_cols[0]])
            return gpd.GeoDataFrame(df.copy(), geometry=geom, crs="EPSG:4326")
        except Exception:
            pass

    return df


# ---------------- Upload ----------------
st.markdown("<h4>📂 Upload Data</h4>", unsafe_allow_html=True)

uploaded_file = st.file_uploader(
    "Upload CSV, Excel, GeoJSON, or KML",
    type=["csv", "xls", "xlsx", "geojson", "json", "kml"]
)

if uploaded_file:

    try:
        name = uploaded_file.name.lower()

        # -------- Read file --------
        if name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
            df = convert_to_geodf(df)

        elif name.endswith((".xls", ".xlsx")):
            df = pd.read_excel(uploaded_file)
            df = convert_to_geodf(df)

        elif name.endswith((".geojson", ".json", ".kml")):
            df = gpd.read_file(uploaded_file)

        else:
            st.error("Unsupported file format")
            st.stop()

        is_spatial = isinstance(df, gpd.GeoDataFrame)

        st.success("✅ File loaded successfully")
        st.dataframe(df.head())

        # ---------------- Split Controls ----------------
        split_col_1 = st.selectbox("Select column to split by", df.columns)

        enable_second_split = st.checkbox("Add another split level")

        split_col_2 = None
        if enable_second_split:
            split_col_2 = st.selectbox(
                "Select second split column",
                [c for c in df.columns if c != split_col_1]
            )

        output_formats = st.multiselect(
            "Select output format(s)",
            ["CSV", "Excel", "GeoJSON", "KML"]
        )

        if ("GeoJSON" in output_formats or "KML" in output_formats) and not is_spatial:
            st.warning("⚠ Spatial formats require valid geometry and will be skipped.")

        # ---------------- Export ----------------
        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:

            for val1, df_lvl1 in df.groupby(split_col_1):
                folder_1 = safe_name(val1)

                # -------- ONE LEVEL SPLIT --------
                if not enable_second_split:
                    base = folder_1

                    if "CSV" in output_formats:
                        zip_file.writestr(
                            f"{base}.csv",
                            df_lvl1.drop(columns="geometry", errors="ignore").to_csv(index=False)
                        )

                    if "Excel" in output_formats:
                        buf = BytesIO()
                        df_lvl1.drop(columns="geometry", errors="ignore").to_excel(buf, index=False)
                        zip_file.writestr(f"{base}.xlsx", buf.getvalue())

                    if is_spatial:
                        spatial = df_lvl1[df_lvl1.geometry.notnull()]
                        if not spatial.empty:
                            spatial = spatial.to_crs(epsg=4326)
                            with tempfile.TemporaryDirectory() as tmp:
                                if "GeoJSON" in output_formats:
                                    path = os.path.join(tmp, f"{base}.geojson")
                                    spatial.to_file(path, driver="GeoJSON")
                                    zip_file.writestr(f"{base}.geojson", open(path, "rb").read())

                                if "KML" in output_formats:
                                    path = os.path.join(tmp, f"{base}.kml")
                                    spatial.to_file(path, driver="KML")
                                    zip_file.writestr(f"{base}.kml", open(path, "rb").read())

                # -------- TWO LEVEL SPLIT --------
                else:
                    for val2, df_lvl2 in df_lvl1.groupby(split_col_2):
                        file_name = safe_name(val2)
                        base = f"{folder_1}/{file_name}"

                        if "CSV" in output_formats:
                            zip_file.writestr(
                                f"{base}.csv",
                                df_lvl2.drop(columns="geometry", errors="ignore").to_csv(index=False)
                            )

                        if "Excel" in output_formats:
                            buf = BytesIO()
                            df_lvl2.drop(columns="geometry", errors="ignore").to_excel(buf, index=False)
                            zip_file.writestr(f"{base}.xlsx", buf.getvalue())

                        if is_spatial:
                            spatial = df_lvl2[df_lvl2.geometry.notnull()]
                            if spatial.empty:
                                continue

                            spatial = spatial.to_crs(epsg=4326)
                            with tempfile.TemporaryDirectory() as tmp:
                                if "GeoJSON" in output_formats:
                                    path = os.path.join(tmp, f"{file_name}.geojson")
                                    spatial.to_file(path, driver="GeoJSON")
                                    zip_file.writestr(f"{base}.geojson", open(path, "rb").read())

                                if "KML" in output_formats:
                                    path = os.path.join(tmp, f"{file_name}.kml")
                                    spatial.to_file(path, driver="KML")
                                    zip_file.writestr(f"{base}.kml", open(path, "rb").read())

        zip_buffer.seek(0)

        st.download_button(
            "⬇ Download Split Files (ZIP)",
            data=zip_buffer,
            file_name="Split_Data.zip",
            mime="application/zip"
        )

    except Exception as e:
        st.error(f"❌ Error: {e}")
