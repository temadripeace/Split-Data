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
st.set_page_config(page_title="Grouped Data Splitting Tool", layout="centered")

# ---------------- Header ----------------
col1, col2, col3 = st.columns([1, 3, 1])
with col2:
    st.image("Sucafina Logo.jpg", width=500)

st.markdown("<h3 style='text-align:center;'>Grouped Data Splitting Tool</h3>", unsafe_allow_html=True)

st.markdown(
    """
    <div style="text-align: justify; font-size: 16px;">
        This tool splits grouped tabular or spatial data by a selected attribute and exports each group as a separate file.
        Supported formats: <b>CSV</b>, <b>Excel</b>, <b>GeoJSON</b>, and <b>KML</b>.
    </div>
    """,
    unsafe_allow_html=True
)

# ---------------- Geometry Conversion ----------------
def convert_to_geodf(df):
    wkt_columns = [
        col for col in df.columns
        if col.lower() in {
            "gps_point", "gps_polygon", "plot_gps_point",
            "plot_gps_polygon", "plot_wkt", "wkt", "geometry"
        }
    ]

    # Try WKT columns
    for wkt_col in wkt_columns:
        try:
            parsed = df[wkt_col].apply(
                lambda x: wkt.loads(str(x))
                if pd.notnull(x) and str(x).strip() != ""
                else None
            )

            if parsed.notnull().any():
                return gpd.GeoDataFrame(
                    df.copy(),
                    geometry=parsed,
                    crs="EPSG:4326"
                )
        except (WKTReadingError, Exception):
            continue

    # Try Lat/Lon fallback
    lon_cols = [c for c in df.columns if "lon" in c.lower()]
    lat_cols = [c for c in df.columns if "lat" in c.lower()]

    if lon_cols and lat_cols:
        try:
            geometry = gpd.points_from_xy(df[lon_cols[0]], df[lat_cols[0]])
            return gpd.GeoDataFrame(df.copy(), geometry=geometry, crs="EPSG:4326")
        except Exception:
            pass

    return df


# ---------------- Upload ----------------
st.markdown("<h4>📂 Upload Data</h4>", unsafe_allow_html=True)

uploaded_file = st.file_uploader(
    "Upload CSV, Excel, GeoJSON, or KML",
    type=["csv", "xls", "xlsx", "geojson", "json", "kml"]
)

if uploaded_file is not None:
    try:
        file_name = uploaded_file.name.lower()
        is_spatial = False

        # -------- Read file --------
        if file_name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
            df = convert_to_geodf(df)

        elif file_name.endswith((".xls", ".xlsx")):
            df = pd.read_excel(uploaded_file)
            df = convert_to_geodf(df)

        elif file_name.endswith((".geojson", ".json", ".kml")):
            df = gpd.read_file(uploaded_file)

        else:
            st.error("Unsupported file format.")
            st.stop()

        # -------- Detect spatial --------
        is_spatial = isinstance(df, gpd.GeoDataFrame)

        st.success("✅ File loaded successfully")
        st.dataframe(df.head())

        # -------- Grouping column --------
        group_col = st.selectbox("Select column to split by", df.columns)

        # -------- Output formats --------
        output_formats = st.multiselect(
            "Select output format(s)",
            ["CSV", "Excel", "GeoJSON", "KML"]
        )

        if ("GeoJSON" in output_formats or "KML" in output_formats) and not is_spatial:
            st.warning("⚠ GeoJSON and KML require valid geometry. They will be skipped.")

        # -------- Create ZIP --------
        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for value, group in df.groupby(group_col):
                clean_name = re.sub(r'[<>:"/\\|?*{}]+', "_", str(value)).strip("_")
                if not clean_name:
                    clean_name = "UNKNOWN"

                # ----- CSV -----
                if "CSV" in output_formats:
                    csv_df = group.drop(columns="geometry", errors="ignore")
                    zip_file.writestr(
                        f"{clean_name}.csv",
                        csv_df.to_csv(index=False)
                    )

                # ----- Excel -----
                if "Excel" in output_formats:
                    excel_buffer = BytesIO()
                    group.drop(columns="geometry", errors="ignore").to_excel(
                        excel_buffer, index=False
                    )
                    zip_file.writestr(
                        f"{clean_name}.xlsx",
                        excel_buffer.getvalue()
                    )

                # ----- Spatial exports -----
                if is_spatial:
                    spatial_group = group[group.geometry.notnull()]

                    if spatial_group.empty:
                        continue

                    spatial_group = spatial_group.to_crs(epsg=4326)

                    with tempfile.TemporaryDirectory() as tmpdir:
                        # GeoJSON
                        if "GeoJSON" in output_formats:
                            geojson_path = os.path.join(tmpdir, f"{clean_name}.geojson")
                            spatial_group.to_file(geojson_path, driver="GeoJSON")
                            with open(geojson_path, "rb") as f:
                                zip_file.writestr(f"{clean_name}.geojson", f.read())

                        # KML
                        if "KML" in output_formats:
                            kml_path = os.path.join(tmpdir, f"{clean_name}.kml")
                            spatial_group.to_file(kml_path, driver="KML")
                            with open(kml_path, "rb") as f:
                                zip_file.writestr(f"{clean_name}.kml", f.read())

        zip_buffer.seek(0)

        st.download_button(
            "⬇ Download Split Files (ZIP)",
            data=zip_buffer,
            file_name="Split_Data.zip",
            mime="application/zip"
        )

    except Exception as e:
        st.error(f"❌ Error: {e}")
