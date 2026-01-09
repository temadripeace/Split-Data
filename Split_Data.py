import streamlit as st
import pandas as pd
import geopandas as gpd
import re
import zipfile
from io import BytesIO




col1, col2, col3 = st.columns([1, 3, 1])  # Left, Center, Right columns
with col2:
    st.image("Sucafina Logo.jpg", width=500)

st.markdown("<h3 style='text-align: center;'>Grouped Data Splitingg Tool</h3>", unsafe_allow_html=True)

# ------------------ App Description ------------------
st.markdown(
    """
    <div style="text-align: justify; font-size: 16px;">
        This tool splits grouped tabular or spatial data by a selected attribute and exports each group as a separate file. 
        It supports imports and exports of <b>CSV</b>, <b>Excel</b>, <b>KML</b>, and <b>GeoJSON</b> file formats.
    </div>
    """,
    unsafe_allow_html=True
)

# ----------------------------------------Convert to GeoDataFrame ----------------------------------------
def convert_to_geodf(df):
    wkt_columns = [col for col in df.columns if col.lower() in [
        "gps_point", "gps_polygon", "plot_gps_point", "plot_gps_polygon", "plot_wkt", "wkt", "geometry"
    ]]
    
    # Try WKT columns one by one
    for wkt_col in wkt_columns:
        try:
            # Attempt to parse WKT only where values are non-null/non-empty
            parsed = df[wkt_col].apply(lambda x: wkt.loads(str(x)) if pd.notnull(x) and str(x).strip() != '' else None)
            # Check if at least one valid geometry parsed
            if parsed.notnull().any():
                df[wkt_col] = parsed
                return gpd.GeoDataFrame(df, geometry=wkt_col, crs="EPSG:4326")
        except Exception as e:
            # Log or show warning but keep trying other columns
            st.warning(f"⚠ Could not parse WKT column '{wkt_col}': {e}")
            continue

    # If no WKT columns succeeded, try lat/lon columns
    lon_candidates = [col for col in df.columns if "lon" in col.lower()]
    lat_candidates = [col for col in df.columns if "lat" in col.lower()]
    if lon_candidates and lat_candidates:
        lon_col = lon_candidates[0]
        lat_col = lat_candidates[0]
        try:
            geometry = gpd.points_from_xy(df[lon_col], df[lat_col])
            return gpd.GeoDataFrame(df.copy(), geometry=geometry, crs="EPSG:4326")
        except Exception as e:
            st.warning(f"⚠ Could not create geometry from lat/lon: {e}")

    st.warning("⚠ No valid geometry found (WKT or Lat/Lon). GeoJSON/KML export may not work.")
    return df



# ------------------ ---------------------File Processing -------------------------------------------------




# ------------------------------------- Streamlit Page Setup ---------------------------------------------
st.set_page_config(page_title="File Viewer", layout="centered")

st.markdown("<h3 style='text-align: left;'>📂 Upload Data</h3>", unsafe_allow_html=True)

# ------------------ -----------Coordinate Processing Functions ------------------------------------------
st.config.set_option('server.maxUploadSize', 2048)
uploaded_file = st.file_uploader(
    "Upload a file",
    type=["csv", "xls", "xlsx", "geojson", "json", "kml"]
)

if uploaded_file is not None:
    try:
        file_name = uploaded_file.name.lower()
        is_spatial = False

        # -----------------------------
        # Read input file
        # -----------------------------
        if file_name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)

        elif file_name.endswith((".xls", ".xlsx")):
            df = pd.read_excel(uploaded_file)

        elif file_name.endswith((".geojson", ".json", ".kml")):
            gdf = gpd.read_file(uploaded_file)
            df = gdf
            is_spatial = True

        else:
            st.error("Unsupported file format.")
            st.stop()

        st.success("✅ File loaded successfully!")
        st.dataframe(df.head())



        
        
        # -----------------------------.............................................................

        if uploaded_file:
    ext = os.path.splitext(uploaded_file.name)[1].lower()

    try:
        # Step 1: Load as plain DataFrame
        if ext == ".csv":
            Data = pd.read_csv(uploaded_file)
        elif ext in [".xlsx", ".xls"]:
            Data = pd.read_excel(uploaded_file)
        elif ext in [".geojson", ".json", ".kml"]:
            gdf_temp = gpd.read_file(uploaded_file, driver="KML" if ext == ".kml" else None)
            Data = pd.DataFrame(gdf_temp)  # Temporarily drop geometry to process as text
            if "geometry" in Data.columns:
                Data["geometry"] = Data["geometry"].apply(lambda g: g.wkt if g is not None else None)
        else:
            st.error("❌ Unsupported file format")
            st.stop()

        # Step 2: Format lat/lon columns
        lat_lon_cols = ['plot_longitude', 'plot_latitude', 'longitute', 'latitute', 'log', 'lat']
        for col in lat_lon_cols:
            if col in Data.columns:
                Data[col] = Data[col].apply(lambda x: format_coord(x) if pd.notnull(x) else x)
                # Convert back to float
                try:
                    Data[col] = Data[col].astype(float)
                except:
                    pass

        # Step 3: Format WKT columns
        wkt_cols = ['plot_gps_point', 'plot_gps_polygon', 'gps_point', 'gps_polygon', 'plot_wkt', 'WKT','wkt', 'geometry', 'Geometry', 'GEOMETRY' ]
        for col in wkt_cols:
            if col in Data.columns:
                Data[col] = Data[col].apply(lambda x: apply_n_times(process_wkt, x, 2) if pd.notnull(x) else x)

        # Step 4: Convert to GeoDataFrame
        Data = convert_to_geodf(Data)

        # Step 5: Display processed data
        st.markdown("<h3 style='text-align: left;'>Processed Data Table</h3>", unsafe_allow_html=True)
        st.dataframe(Data)






        
        # Grouping column
        # -----------------------------
        group_col = st.selectbox(
            "Select grouped column to split by",
            df.columns
        )       
        # -----------------------------
        # Output formats
        # -----------------------------
        output_formats = st.multiselect(
            "Select output format(s)",
            ["CSV", "Excel", "GeoJSON", "KML"],
            default=[]
        )

        if ("GeoJSON" in output_formats or "KML" in output_formats) and not is_spatial:
            st.warning("⚠️ GeoJSON and KML require geometry. They will be skipped.")

        # -----------------------------
        # Create ZIP
        # -----------------------------
        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for value, group in df.groupby(group_col):
                value_str = str(value)
                clean_name = re.sub(r'[<>:"/\\|?*{}]+', "_", value_str).strip("_")
                if not clean_name:
                    clean_name = "UNKNOWN"

                # CSV
                if "CSV" in output_formats:
                    csv_data = (
                        group.drop(columns="geometry")
                        if is_spatial else group
                    ).to_csv(index=False)
                    zip_file.writestr(f"{clean_name}.csv", csv_data)

                # Excel
                if "Excel" in output_formats:
                    excel_buffer = BytesIO()
                    (
                        group.drop(columns="geometry")
                        if is_spatial else group
                    ).to_excel(excel_buffer, index=False)
                    zip_file.writestr(f"{clean_name}.xlsx", excel_buffer.getvalue())

                # GeoJSON
                if "GeoJSON" in output_formats and is_spatial:
                    geojson_buffer = BytesIO()
                    group.to_file(geojson_buffer, driver="GeoJSON")
                    zip_file.writestr(f"{clean_name}.geojson", geojson_buffer.getvalue())

                # KML
                if "KML" in output_formats and is_spatial:
                    kml_buffer = BytesIO()
                    group.to_file(kml_buffer, driver="KML")
                    zip_file.writestr(f"{clean_name}.kml", kml_buffer.getvalue())

        zip_buffer.seek(0)

        st.download_button(
            "⬇Download Files (ZIP)",
            data=zip_buffer,
            file_name="Split_Data.zip",
            mime="application/zip"
        )

    
    except Exception as e:

        st.error(f"❌ Error: {e}")















