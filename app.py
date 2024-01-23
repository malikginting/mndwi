import streamlit as st
import ee
import geemap
import folium
from folium import WmsTileLayer
from streamlit_folium import folium_static
from datetime import datetime, timedelta
import json

st.set_page_config(
    page_title="MNDWI Viewer",
    page_icon="https://cdn-icons-png.flaticon.com/128/2557/2557012.png",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get help': "https://github.com/IndigoWizard/MNDWI-Viewer",
        'Report a bug': "https://github.com/IndigoWizard/NDVI-Viewer/issues",
        'About': "This app was developped by [IndigoWizard](https://github.com/IndigoWizard/NDVI-Viewer) for the purpose of environmental monitoring and geospatial analysis"
        
    }
)

st.markdown(
"""
<style>
    /* Header*/
    .st-emotion-cache-1avcm0n{
        height: 1rem;
    }
    /* Smooth scrolling*/
    .main {
        scroll-behavior: smooth;
    }
    /* main app body with less padding*/
    .st-emotion-cache-z5fcl4 {
        padding-block: 0;
    }

    /*Sidebar*/
    .st-emotion-cache-10oheav {
        padding: 0 1rem;
    }

    /*Sidebar : inside container*/
    .css-ge7e53 {
        width: fit-content;
    }

    /*Sidebar : image*/
    .css-1kyxreq {
        display: block !important;
    }

    /*Sidebar : Navigation list*/
    div.element-container:nth-child(4) > div:nth-child(1) > div:nth-child(1) > ul:nth-child(1) {
        margin: 0;
        padding: 0;
        list-style: none;
    }
    div.element-container:nth-child(4) > div:nth-child(1) > div:nth-child(1) > ul:nth-child(1) > li {
        padding: 0;
        margin: 0;
        padding: 0;
        font-weight: 600;
    }
    div.element-container:nth-child(4) > div:nth-child(1) > div:nth-child(1) > ul:nth-child(1) > li > a {
        text-decoration: none;
        transition: 0.2s ease-in-out;
        padding-inline: 10px;
    }
    
    div.element-container:nth-child(4) > div:nth-child(1) > div:nth-child(1) > ul:nth-child(1) > li > a:hover {
        color: rgb(46, 206, 255);
        transition: 0.2s ease-in-out;
        background: #131720;
        border-radius: 4px;
    }
    
    /* Sidebar: socials*/
    div.css-rklnmr:nth-child(6) > div:nth-child(1) > div:nth-child(1) > p {
        display: flex;
        flex-direction: row;
        gap: 1rem;
    }

    /* Upload info box */
    /*Upload button: dark theme*/
    .st-emotion-cache-1erivf3 {
        display: flex;
        flex-direction: column;
        align-items: inherit;
        font-size: 14px;
    }
    .css-u8hs99.eqdbnj014 {
        display: flex;
        flex-direction: row;
        margin-inline: 0;
    }
    /*Upload button: light theme*/
    .st-emotion-cache-1gulkj5 {
        display: flex;
        flex-direction: column;
        align-items: inherit;
        font-size: 14px;
    }

    .st-emotion-cache-u8hs99 {
        display: flex;
        flex-direction: row;
        margin-inline: 0;
    }
    /*Legend style*/

    .mndwilegend {
        transition: 0.2s ease-in-out;
        border-radius: 5px;
        box-shadow: 0 0 5px rgba(0, 0, 0, 0.2);
        background: rgba(0, 0, 0, 0.05);
    }
    .mndwilegend:hover {
        transition: 0.3s ease-in-out;
        box-shadow: 0 0 5px rgba(0, 0, 0, 0.8);
        background: rgba(0, 0, 0, 0.12);
        cursor: pointer;
    }
    .reclassifiedmndwi {
        transition: 0.2s ease-in-out;
        border-radius: 5px;
        box-shadow: 0 0 5px rgba(0, 0, 0, 0.2);
        background: rgba(0, 0, 0, 0.05);
    }
    .reclassifiedmndwi:hover {
        transition: 0.3s ease-in-out;
        box-shadow: 0 0 5px rgba(0, 0, 0, 0.8);
        background: rgba(0, 0, 0, 0.12);
        cursor: pointer;
    }
    
    /*Form submit button: generate map*/
    button.st-emotion-cache-19rxjzo:nth-child(1) {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# Initializing the Earth Engine library
# Use ee.Initialize() only on local machine! Comment back before deployement (Unusable on deployment > use geemap init+auth bellow)
#ee.Initialize()
# geemap auth + initialization for cloud deployment
@st.cache_data(persist=True)
def ee_authenticate(token_name="EARTHENGINE_TOKEN"):
    geemap.ee_initialize(token_name=token_name)

ee.Initialize(project='ee-malik')

# Earth Engine drawing method setup
def add_ee_layer(self, ee_image_object, vis_params, name):
    map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
    layer = folium.raster_layers.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Map Data &copy; <a href="https://earthengine.google.com/">Google Earth Engine</a>',
        name=name,
        overlay=True,
        control=True
    )
    layer.add_to(self)
    return layer

# Configuring Earth Engine display rendering method in Folium
folium.Map.add_ee_layer = add_ee_layer

# Defining a function to create and filter a GEE image collection for results
def satCollection(cloudRate, initialDate, updatedDate, aoi):
    collection = ee.ImageCollection('COPERNICUS/S2_SR') \
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloudRate)) \
        .filterDate(initialDate, updatedDate) \
        .filterBounds(aoi)
    
    # Defining a function to clip the colleciton to the area of interst
    def clipCollection(image):
        return image.clip(aoi).divide(10000)
    # clipping the collection
    collection = collection.map(clipCollection)
    return collection

# Upload function
# Define a global variable to store the centroid of the last uploaded geometry
last_uploaded_centroid = None
def upload_files_proc(upload_files):
    # A global variable to track the latest geojson uploaded
    global last_uploaded_centroid
    # Setting up a variable that takes all polygons/geometries within the same/different geojson
    geometry_aoi_list = []

    for upload_file in upload_files:
        bytes_data = upload_file.read()
        geojson_data = json.loads(bytes_data)

        if 'features' in geojson_data and isinstance(geojson_data['features'], list):
            # Handle GeoJSON files with a 'features' list
            features = geojson_data['features']
        elif 'geometries' in geojson_data and isinstance(geojson_data['geometries'], list):
            # Handle GeoJSON files with a 'geometries' list
            features = [{'geometry': geo} for geo in geojson_data['geometries']]
        else:
            # handling cases of unexpected file format or missing 'features' or 'geometries'
            continue

        for feature in features:
            if 'geometry' in feature and 'coordinates' in feature['geometry']:
                coordinates = feature['geometry']['coordinates']
                geometry = ee.Geometry.Polygon(coordinates) if feature['geometry']['type'] == 'Polygon' else ee.Geometry.MultiPolygon(coordinates)
                geometry_aoi_list.append(geometry)

                # Update the last uploaded centroid
                last_uploaded_centroid = geometry.centroid(maxError=1).getInfo()['coordinates']

    if geometry_aoi_list:
        geometry_aoi = ee.Geometry.MultiPolygon(geometry_aoi_list)
    else:
        geometry_aoi = ee.Geometry.Point([27.98, 36.13])

    return geometry_aoi


# Time input processing function
def date_input_proc(input_date, time_range):
    end_date = input_date
    start_date = input_date - timedelta(days=time_range)
    
    str_start_date = start_date.strftime('%Y-%m-%d')
    str_end_date = end_date.strftime('%Y-%m-%d')
    return str_start_date, str_end_date

# Main function to run the Streamlit app
def main():
    # initiate gee 
    ee_authenticate(token_name="EARTHENGINE_TOKEN")

    # sidebar
    with st.sidebar:
        st.title("MNDWI Viewer App")
        st.image("https://cdn-icons-png.flaticon.com/128/2557/2557012.png", width=90)
        st.subheader("Navigation:")
        st.markdown(
            """
                - [MNDWI Map](#mndwi-viewer)
                - [Map Legend](#map-legend)
                - [Process workflow](#process-workflow-aoi-date-range-and-classification)
                - [Interpreting the Results](#interpreting-the-results)
                - [Environmental Index](#using-an-environmental-index-mndwi)
                - [Data](#data-landsat-8-imagery-and-l2a-product)
                - [Contribution](#contribute-to-the-app)
                - [About](#about)
                - [Credit](#credit)
            """)
    
        
    with st.container():
        st.title("MNDWI Viewer")
        st.markdown("**Monitor Flood by Viewing & Comparing mndwi Values Through Time and Location with Landsat 8 Satellite Images on The Fly!**")
    
    with st.form("input_form"):
        c1, c2 = st.columns([3, 1])
        #### User input section - START
        
        with st.container():
            with c2:
            ## Cloud coverage input
                st.info("Cloud Coverage 🌥️")
                cloud_pixel_percentage = st.slider(label="cloud pixel rate", min_value=5, max_value=100, step=5, value=85 , label_visibility="collapsed")
                
            ## File upload
                # User input GeoJSON file
                st.info("Upload Area Of Interest file:")
                upload_files = st.file_uploader("Crete a GeoJSON file at: [geojson.io](https://geojson.io/)", accept_multiple_files=True)
                # calling upload files function
                geometry_aoi = upload_files_proc(upload_files)
            
            ## Accessibility: Color palette input
                st.info("Custom Color Palettes")
                accessibility = st.selectbox("Accessibility: Colorblind-friendly Palettes", ["Normal", "Non Banjir", "Banjir Ringan", "Banjir Sedang", "Banjir Tinggi"])

                # Define default color palettes: used in map layers & map legend
                default_mndwi_palette = ["#ffffe5", "#f7fcb9", "#78c679", "#41ab5d", "#238443", "#005a32"]
                default_reclassified_mndwi_palette = ["#a50026","#ed5e3d","#f9f7ae","#f4ff78","#9ed569","#229b51","#006837"]

                # a copy of default colors that can be reaffected
                mndwi_palette = default_mndwi_palette.copy() 
                reclassified_mndwi_palette = default_reclassified_mndwi_palette.copy()

                if accessibility == "Non Banjir":
                    mndwi_palette = ["#fffaa1","#f4ef8e","#9a5d67","#573f73","#372851","#191135"]
                    reclassified_mndwi_palette = ["#95a600","#92ed3e","#affac5","#78ffb0","#69d6c6","#22459c","#000e69"]
                elif accessibility == "Banjir Ringan":
                    mndwi_palette = ["#a6f697","#7def75","#2dcebb","#1597ab","#0c677e","#002c47"]
                    reclassified_mndwi_palette = ["#95a600","#92ed3e","#affac5","#78ffb0","#69d6c6","#22459c","#000e69"]
                elif accessibility == "Banjir Sedang":
                    mndwi_palette = ["#cdffd7","#a1fbb6","#6cb5c6","#3a77a5","#205080","#001752"]
                    reclassified_mndwi_palette = ["#ed4700","#ed8a00","#e1fabe","#99ff94","#87bede","#2e40cf","#0600bc"]
                elif accessibility == "Banjir Tinggi":
                    mndwi_palette = ["#407de0", "#2763da", "#394388", "#272c66", "#16194f", "#010034"]
                    reclassified_mndwi_palette = ["#004f3d", "#338796", "#66a4f5", "#3683ff", "#3d50ca", "#421c7f", "#290058"]

        with st.container():
            ## Time range input
            with c1:
                col1, col2 = st.columns(2)
                
                # Creating a 2 days delay for the date_input placeholder to be sure there are satellite images in the dataset on app start
                today = datetime.today()
                delay = today - timedelta(days=2)

                # Date input widgets
                col1.warning("Initial mndwi Date 📅")
                initial_date = col1.date_input("initial", value=delay, label_visibility="collapsed")

                col2.success("Updated mndwi Date 📅")
                updated_date = col2.date_input("updated", value=delay, label_visibility="collapsed")

                # Setting up the time range variable for an image collection
                time_range = 7
                # Process initial date
                str_initial_start_date, str_initial_end_date = date_input_proc(initial_date, time_range)

                # Process updated date
                str_updated_start_date, str_updated_end_date = date_input_proc(updated_date, time_range)
    
    #### User input section - END

            #### Map section - START
            global last_uploaded_centroid

            # Create the initial map
            if last_uploaded_centroid is not None:
                latitude = last_uploaded_centroid[1]
                longitude = last_uploaded_centroid[0]
                m = folium.Map(location=[latitude, longitude], tiles=None, zoom_start=12, control_scale=True)
            else:
                # Default location if no file is uploaded
                m = folium.Map(location=[36.45, 10.85], tiles=None, zoom_start=4, control_scale=True)


            ### BASEMAPS - START
            ## Primary basemaps
            # OSM
            b0 = folium.TileLayer('Open Street Map', name="Open Street Map")
            b0.add_to(m)
            # CartoDB Dark Matter basemap
            b1 = folium.TileLayer('cartodbdark_matter', name='Dark Basemap')
            b1.add_to(m)

            #### Satellite imagery Processing Section - START
            ## Defining and clipping image collections for both dates:
            # initial Image collection
            initial_collection = satCollection(cloud_pixel_percentage, str_initial_start_date, str_initial_end_date, geometry_aoi)
            # updated Image collection
            updated_collection = satCollection(cloud_pixel_percentage, str_updated_start_date, str_updated_end_date, geometry_aoi)

            # setting a sat_imagery variable that could be used for various processes later on (tci, mndwi... etc)
            initial_sat_imagery = initial_collection.median()
            updated_sat_imagery = updated_collection.median()

            ## TCI (True Color Imagery)
            # Clipping the image to the area of interest "aoi"
            initial_tci_image = initial_sat_imagery
            updated_tci_image = updated_sat_imagery

            # TCI image visual parameters
            tci_params = {
            'bands': ['B4', 'B3', 'B2'], #using Red, Green & Blue bands for TCI.
            'min': 0,
            'max': 1,
            'gamma': 1
            }

            ## Other imagery processing operations go here 
            # mndwi
            def getmndwi(collection):
                green_band = 'B3'  # Update with the correct band name for red
                swir_band = 'B11'  # Update with the correct band name for SWIR
                return collection.normalizedDifference(['B3', 'B11'])

            # clipping to AOI
            initial_mndwi = getmndwi(initial_sat_imagery)
            updated_mndwi = getmndwi(updated_sat_imagery)

            # mndwi visual parameters:
            mndwi_params = {
            'min': 0,
            'max': 1,
            'palette': mndwi_palette
            }

            # Masking mndwi over the water & show only land
            def satImageMask(sat_image):
                masked_image = sat_image.updateMask(sat_image.gte(0))
                return masked_image
            
            # Mask mndwi images
            initial_mndwi = satImageMask(initial_mndwi)
            updated_mndwi = satImageMask(updated_mndwi)

            # ##### mndwi classification: 7 classes
            def classify_mndwi(masked_image): # better use a masked image to avoid water bodies obstracting the result as possible
                mndwi_classified = ee.Image(masked_image) \
                .where(masked_image.gte(-1).And(masked_image.lt(-0.1)), 1) \
                .where(masked_image.gte(0).And(masked_image.lt(0.2)), 2) \
                .where(masked_image.gte(0.21).And(masked_image.lt(0.35)), 3) \
                .where(masked_image.gte(0.35).And(masked_image.lt(0.45)), 4) \
                .where(masked_image.gte(0.45).And(masked_image.lt(0.65)), 5)             
                return mndwi_classified

            # Classify masked mndwi
            initial_mndwi_classified = classify_mndwi(initial_mndwi)
            updated_mndwi_classified = classify_mndwi(updated_mndwi)

            # Classified mndwi visual parameters
            mndwi_classified_params = {
            'min': 1,
            'max': 7,
            'palette': reclassified_mndwi_palette
            # each color corresponds to an mndwi class.
            }

            #### Satellite imagery Processing Section - END

            #### Layers section - START
            # Check if the initial and updated dates are the same
            if initial_date == updated_date:
                # Only display the layers based on the updated date without dates in their names
                m.add_ee_layer(updated_tci_image, tci_params, 'Satellite Imagery')
                m.add_ee_layer(updated_mndwi, mndwi_params, 'Raw mndwi')
                m.add_ee_layer(updated_mndwi_classified, mndwi_classified_params, 'Reclassified mndwi')
            else:
                # Show both dates in the appropriate layers
                # Satellite image
                m.add_ee_layer(initial_tci_image, tci_params, f'Initial Satellite Imagery: {initial_date}')
                m.add_ee_layer(updated_tci_image, tci_params, f'Updated Satellite Imagery: {updated_date}')

                # mndwi
                m.add_ee_layer(initial_mndwi, mndwi_params, f'Initial Raw mndwi: {initial_date}')
                m.add_ee_layer(updated_mndwi, mndwi_params, f'Updated Raw mndwi: {updated_date}')

                # Add layers to the second map (m.m2)
                # Classified mndwi
                m.add_ee_layer(initial_mndwi_classified, mndwi_classified_params, f'Initial Reclassified mndwi: {initial_date}')
                m.add_ee_layer(updated_mndwi_classified, mndwi_classified_params, f'Updated Reclassified mndwi: {updated_date}')


            #### Layers section - END

            #### Map result display - START
            # Folium Map Layer Control: we can see and interact with map layers
            folium.LayerControl(collapsed=True).add_to(m)
            # Display the map
        submitted = c2.form_submit_button("Generate map")
        if submitted:
            with c1:
                folium_static(m)
        else:
            with c1:
                folium_static(m)

    #### Map result display - END

    #### Legend - START
    with st.container():
        st.subheader("Map Legend:")
        col3, col4, col5 = st.columns([1,2,1])

        with col3:            
            # Create an HTML legend for mndwi classes
            mndwi_legend_html = """
                <div class="mndwilegend">
                    <h5>Raw mndwi</h5>
                    <div style="display: flex; flex-direction: row; align-items: flex-start; gap: 1rem; width: 100%;">
                        <div style="width: 30px; height: 200px; background: linear-gradient({0},{1},{2},{3},{4},{5});"></div>
                        <div style="display: flex; flex-direction: column; justify-content: space-between; height: 200px;">
                            <span>-1</span>
                            <span style="align-self: flex-end;">1</span>
                        </div>
                    </div>
                </div>
            """.format(*mndwi_palette)

            # Display the mndwi legend using st.markdown
            st.markdown(mndwi_legend_html, unsafe_allow_html=True)

        with col4:            
            # Create an HTML legend for mndwi classes
            reclassified_mndwi_legend_html = """
                <div class="reclassifiedmndwi">
                    <h5>mndwi Classes</h5>
                    <ul style="list-style-type: none; padding: 0;">
                        <li style="margin: 0.2em 0px; padding: 0;"><span style="color: {0};">&#9632;</span> Vegetasi lainnya. (/Built-up/Rocks/Sand Surfaces)</li>
                        <li style="margin: 0.2em 0px; padding: 0;"><span style="color: {1};">&#9632;</span> Non Banjir</li>
                        <li style="margin: 0.2em 0px; padding: 0;"><span style="color: {2};">&#9632;</span> Banjir Ringan</li>
                        <li style="margin: 0.2em 0px; padding: 0;"><span style="color: {3};">&#9632;</span> Banjir Sedang.</li>
                        <li style="margin: 0.2em 0px; padding: 0;"><span style="color: {4};">&#9632;</span> Banjir Tinggi</li>
                    </ul>
                </div>
            """.format(*reclassified_mndwi_palette)

            # Display the Reclassified mndwi legend using st.markdown
            st.markdown(reclassified_mndwi_legend_html, unsafe_allow_html=True)

    #### Legend - END

    #### Miscs Infos - START
    st.subheader("Information")

    ## How It Works
    st.write("#### Process workflow: AOI, Date Range, and Classification")
    st.write("This app provides a simple interface to explore mndwi changes over time for a specified Area of Interest (AOI). Here's how it works:")

    st.write("1. **Upload GeoJSON AOI:** Start by uploading a GeoJSON file that outlines your Area of Interest. This defines the region where mndwi analysis will be performed. You can create any polygon-shaped area of interest at [geojson.io](https://geojson.io).")
    st.write("2. **Select Date Range:** Choose a date, this input triggers the app to gather images from a **7-days range** leading to that date. These images blend into a mosaic that highlights vegetation patterns while minimizing disruptions like clouds. ")
    st.write("3. **Select Cloud Coverate Rate:** Choose a value for cloud coverage, this input triggers the app to gather images with relevant value of clouds covering the images. A higher value will gather more images but may be of poor quality, lower cloud coverage value gathers clearer images, but may have less images in the collection.")
    st.write("4. **Image Collection and Processing:** Once the date range is established, the app collects satellite images spanning that period. These images are then clipped to your chosen Area of Interest (AOI) and undergo processing to derive raw mndwi values using wavelength calculations. This method ensures that the resulting mndwi map accurately reflects the vegetation status within your specific region of interest.")
    st.write("5. **mndwi Classification:** The raw mndwi results are classified into distinct vegetation classes. This classification provides a simplified visualization of vegetation density, aiding in interpretation.")
    st.write("6. **Map Visualization:** The results are displayed on an interactive map, allowing you to explore mndwi patterns and changes within your AOI.")

    st.write("This app is designed to provide an accessible tool for both technical and non-technical users to explore and interpret vegetation health and density changes.")
    st.write("Keep in mind that while the mndwi map is a valuable tool, its interpretation requires consideration of various factors. Enjoy exploring the world of vegetation health and density!")

    # Results interpretation
    st.write("#### Interpreting the Results")
    st.write("When exploring the mndwi map, keep in mind:")

    st.write("- Clouds, atmospheric conditions, and water bodies can affect the map's appearance.")
    st.write("- Satellite sensors have limitations in distinguishing surface types, leading to color variations.")
    st.write("- mndwi values vary with seasons, growth stages, and land cover changes.")
    st.write("- The map provides visual insights rather than precise representations.")

    st.write("Understanding these factors will help you interpret the results more effectively. This application aims to provide you with an informative visual aid for water vegetation analysis.")

    ## mndwi/Environmental Index
    st.write("#### Using an Environmental Index - mndwi:")
    st.write("The [Modified Normalized Difference Water Index (mndwi)](https://eos.com/make-an-analysis/mndwi/) is an essential environmental index that provides insights into the water of vegetation. It is widely used in remote sensing and geospatial analysis to monitor changes in land cover, vegetation growth, and environmental conditions.")

    st.write("mndwi is calculated using satellite imagery that captures both SNear-Infrared **(SWIR)** and Green **(G)** wavelengths. The formula is:")
    st.latex(r'''
    \text{mndwi} = \frac{\text{SWIR} - \text{G}}{\text{SWIR} + \text{G}}
    ''')

    st.write("mndwi values range from **[-1** to **1]**, with higher values indicating water vegetation.")

    ## Data
    st.write("#### Data: Landsat 8 Imagery and L2A Product")
    st.write("This app utilizes **Landsat 8 atmospherically corrected Surface Reflectance images**.")

    
    #### Miscs Info - END

    #### Contributiuon - START
    st.header("Contribute to the App")
    con1, con2 = st.columns(2)
    con1.image("https://www.pixenli.com/image/SoL3iZMG")
    con2.markdown("""
        Contributions are welcome from the community to help improve this app! Whether you're interested in fixing bugs 🐞, implementing a new feature 🌟, or enhancing the user experience 🪄, your contributions are valuable.
                  
        The project is listed under **Hacktoberfest** lalbel for those of you [Hacktoberfest](https://hacktoberfest.com/) enthusiasts! Since the reward for contributing 4 PRs is getting a tree planted in your name through [TreeNation](https://tree-nation.com/), I see it fits the theme of this project.
        """)
    st.markdown("""
        #### Ways to Contribute

        - **Report Issues**: If you come across any bugs, issues, or unexpected behavior, please report them in the [GitHub Issue Tracker](https://github.com/IndigoWizard/mndwi-Viewer/issues).

        - **Suggest Enhancements**: Have an idea to make the app better? Share your suggestions in the [GitHub Issue Tracker](https://github.com/IndigoWizard/mndwi-Viewer/issues).

        - **Code Contributions**: If you're comfortable with coding, you can contribute by submitting pull requests against the `dev` branch of the [Project's GitHub repository](https://github.com/IndigoWizard/mndwi-Viewer/).
    """)

    #### Contributiuon - START

    #### About App - START
    st.subheader("About:")
    st.markdown("This project was first developed by me ([IndigoWizard](https://github.com/IndigoWizard)) and [Emmarie-Ahtunan](https://github.com/Emmarie-Ahtunan) as a submission to the **Environemental Data Challenge** of [Global Hack Week: Data](https://ghw.mlh.io/) by [Major League Hacking](https://mlh.io/).<br> I continued developing the base project to make it a feature-complete app. Check the project's GitHub Repo here: [IndigoWizard/mndwi-Viewer](https://github.com/IndigoWizard/mndwi-Viewer)",  unsafe_allow_html=True)
    st.image("https://www.pixenli.com/image/Hn1xkB-6")
    #### About App - END

    #### Credit - START
    st.subheader("Credit:")
    st.markdown("""The app was developped by [IndigoWizard](https://github.com/IndigoWizard) using; [Streamlit](https://streamlit.io/), [Google Earth Engine](https://github.com/google/earthengine-api) Python API, [geemap](https://github.com/gee-community/geemap), [Folium](https://github.com/python-visualization/folium). Agriculture icons created by <a href="https://www.flaticon.com/free-icons/agriculture" title="agriculture icons">dreamicons - Flaticon</a>""", unsafe_allow_html=True)
    #### Credit - END
    
    ##### Custom Styling
    st.markdown(
    """
    <style>
        /*Map iframe*/
        iframe {
            width: 100%;
        }
        .css-1o9kxky.e1f1d6gn0 {
            border: 2px solid #ffffff4d;
            border-radius: 4px;
            padding: 1rem;
        }
    </style>
    """, unsafe_allow_html=True)
 

# Run the app
if __name__ == "__main__":
    main()
