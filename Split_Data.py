import streamlit as st
import pandas as pd
import geopandas as gpd
import re
import zipfile
from io import BytesIO




col1, col2, col3 = st.columns([1, 3, 1])  # Left, Center, Right columns
with col2:
    st.image("Sucafina Logo.jpg", width=500)

st.markdown("<h3 style='text-align: center;'>Geographic Coordinate Formatting Tool - 6DP</h3>", unsafe_allow_html=True)

# ------------------ App Description ------------------




st.set_page_config(page_title="Split Data by Country", layout="centered")

st.title("🌍 Split CSV / Excel / GeoJSON / KML by Country")

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

        # -----------------------------
        # Grouping column
        # -----------------------------
        group_col = st.selectbox(
            "Select column to group by",
            df.columns,
            index=df.columns.get_loc("Country") if "Country" in df.columns else 0
        )

        # -----------------------------
        # Output formats
        # -----------------------------
        output_formats = st.multiselect(
            "Select output format(s)",
            ["CSV", "Excel", "GeoJSON", "KML"],
            default=["CSV"]
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
            "⬇️ Download grouped files (ZIP)",
            data=zip_buffer,
            file_name="grouped_output_files.zip",
            mime="application/zip"
        )

    except Exception as e:

        st.error(f"❌ Error: {e}")
