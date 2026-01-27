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
        Upload a file or a ZIP folder containing multiple CSV, Excel, GeoJSON, or KML files.
        All files will be merged into a single dataset before splitting.
        Output formats: <b>CSV</b>, <b>Excel</b>, <b>GeoJSON</b>, <b>KML</b>.
    </div>
    """,
    unsafe_allow_html=True
)

# ---------------- Helpers ----------------
def safe_name(value):
    """Sanitize filenames for safe paths"""
    name = re.sub(r'[<>:"/\\|?*{}]+', "_", str(value)).strip("_")
    return name if name else "UNKNOWN"

def convert_to_geodf(df):
    """Convert DataFrame to GeoDataFrame if it has WKT or lat/lon columns"""
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
                lambda x: wkt.loads(str(x)) if pd.notnull(x) and str(x).strip() != "" else None
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

# ---------------- Cache Data Loading ----------------
@st.cache_data(show_spinner=True)
def load_and_merge_files(uploaded_file):
    """Load CSV/Excel/GeoJSON/KML files from a ZIP or single file and merge them immediately"""
    all_dfs = []
    file_count = 0

    def process_file(file_path):
        nonlocal file_count
        try:
            ext = file_path.lower().split('.')[-1]
            if ext in ["csv", "txt"]:
                df = pd.read_csv(file_path)
            elif ext in ["xls", "xlsx"]:
                df = pd.read_excel(file_path)
            elif ext in ["geojson", "json", "kml"]:
                df = gpd.read_file(file_path)
            else:
                return None
            df = convert_to_geodf(df)
            if df is not None:
                file_count += 1
            return df
        except:
            return None

    # -------- Handle ZIP --------
    if uploaded_file.name.lower().endswith(".zip"):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(uploaded_file, "r") as zip_ref:
                zip_ref.extractall(tmp_dir)

            # Walk recursively and process files on the fly
            for root, dirs, files in os.walk(tmp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    df = process_file(file_path)
                    if df is not None:
                        all_dfs.append(df)
    else:
        # Single file
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_path = os.path.join(tmp_dir, uploaded_file.name)
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            df = process_file(temp_path)
            if df is not None:
                all_dfs.append(df)

    if not all_dfs:
        return None, 0

    # Merge all files
    is_spatial = any(isinstance(d, gpd.GeoDataFrame) for d in all_dfs)
    if is_spatial:
        combined_df = gpd.GeoDataFrame(pd.concat(all_dfs, ignore_index=True), crs="EPSG:4326")
    else:
        combined_df = pd.concat(all_dfs, ignore_index=True)

    return combined_df, file_count

# ---------------- Upload ----------------
uploaded_file = st.file_uploader(
    "Upload CSV, Excel, GeoJSON, KML, or a ZIP folder",
    type=["csv", "xls", "xlsx", "geojson", "json", "kml", "zip"]
)

if uploaded_file:
    combined_df, file_count = load_and_merge_files(uploaded_file)
    if combined_df is None:
        st.error("❌ No valid files found to merge.")
        st.stop()

    st.success(f"✅ File(s) loaded and merged successfully ({file_count} files)")
    st.dataframe(combined_df.head())

    # ---------------- Split Controls ----------------
    split_col_1 = st.selectbox("Select column to split by", combined_df.columns)
    enable_second_split = st.checkbox("Add another split level")
    split_col_2 = None
    if enable_second_split:
        split_col_2 = st.selectbox(
            "Select second split column",
            [c for c in combined_df.columns if c != split_col_1]
        )

    output_formats = st.multiselect(
        "Select output format(s)",
        ["CSV", "Excel", "GeoJSON", "KML"]
    )

    is_spatial = isinstance(combined_df, gpd.GeoDataFrame)
    if ("GeoJSON" in output_formats or "KML" in output_formats) and not is_spatial:
        st.warning("⚠ Spatial formats require valid geometry and will be skipped.")

    # ---------------- Export ----------------
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for val1, df_lvl1 in combined_df.groupby(split_col_1):
            folder_1 = safe_name(val1)

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
