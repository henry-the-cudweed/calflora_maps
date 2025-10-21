#
#
# run this by using Python Console in ArcGIS, run the following code just in one line
#
#APIkey = "insert your key"; import requests; exec(requests.get("https://raw.githubusercontent.com/henry-the-cudweed/calflora_maps/refs/heads/main/calflora_map.py").text, globals())
#
#
# you will also have to create a symbology layer beforehand

import arcpy
import requests
import os
from arcpy import env
from arcpy.da import InsertCursor

MGP_shapeID = "rs1515"

# Define workspace and geodatabase
workspace = r'C:\GIS\CalfloraProject'
gdb_name = 'CalfloraData.gdb'
gdb_path = os.path.join(workspace, gdb_name)

# Ensure workspace exists
if not os.path.exists(workspace):
    os.makedirs(workspace)

# Create geodatabase if it doesn't exist
if not arcpy.Exists(gdb_path):
    arcpy.CreateFileGDB_management(workspace, gdb_name)
    print(f"Created geodatabase: {gdb_path}")
else:
    print(f"Using existing geodatabase: {gdb_path}")

# Feature class settings
fc_name = "Calflora_Polygons"
fc_path = os.path.join(gdb_path, fc_name)

# Create feature class if it doesn't exist
if not arcpy.Exists(fc_path):
    arcpy.CreateFeatureclass_management(gdb_path, fc_name, "POLYGON", spatial_reference=4326)
    arcpy.AddField_management(fc_path, "CommonName", "TEXT")
    arcpy.AddField_management(fc_path, "Taxon", "TEXT")
    arcpy.AddField_management(fc_path, "Observer", "TEXT")
    arcpy.AddField_management(fc_path, "PercentCover", "TEXT")
    print(f"Created feature class: {fc_path}")
else:
    print(f"Using existing feature class: {fc_path}")

# Define additional parameters for limiting the search
params = {
    'csetId': 291,
    'shapeId': MGP_shapeID
}
plantlist_id = 'px1436'

# Define API endpoint with the plant list filter
api_url = f"https://api.calflora.org/observations?plantlistId={plantlist_id}&maxResults=10"

# Send the request with the additional parameters
headers = {"X-Api-Key": "CKLjKHH1nVZMlC8tsu"}
response = requests.get(api_url, headers=headers, params=params)

# Check the status and handle the response
if response.status_code == 200:
    data = response.json()
    print(f"Fetched {len(data)} records from the API.")
else:
    print("Error fetching data from API:", response.text)
    data = []

# Function to convert percent cover range to a numeric value (average of the range)
def convert_percent_cover(cover_str):
    if cover_str:
        range_values = cover_str.split(" - ")
        if len(range_values) == 2:
            try:
                low = float(range_values[0])
                high = float(range_values[1])
                return (low + high) / 2
            except ValueError:
                pass
    return 0

# Function to get polygon geometry (polygon or buffered line)
def get_polygon_from_wkt(record):
    wkt = record.get("Reference Polygon")
    if not wkt:
        return None

    # Handle polygon geometry directly
    if wkt.startswith("POLYGON"):
        return arcpy.FromWKT(wkt)

    # Handle line geometry with buffering
    elif wkt.startswith("LINESTRING"):
        try:
            line_geom = arcpy.FromWKT(wkt)

            # Get radius from record, default to 3 meters if missing or invalid
            raw_radius = record.get("radius", None)
            try:
                radius_m = float(raw_radius) if raw_radius not in (None, "") else 0
            except ValueError:
                radius_m = 0

            if radius_m <= 0:
                radius_m = 3  # default buffer radius

            # Project to local UTM (Zone 10N) for accurate buffering
            projected_line = line_geom.projectAs(arcpy.SpatialReference(26910))
            buffered = projected_line.buffer(radius_m)

            # Reproject back to WGS84
            return buffered.projectAs(arcpy.SpatialReference(4326))

        except Exception as e:
            print(f"Error buffering LINESTRING: {e}")
            return None

    else:
        print(f"Unsupported geometry type: {wkt[:30]}")
        return None

# Delete all existing rows from the feature class to avoid accumulation of old data
if arcpy.Exists(fc_path):
    with arcpy.da.UpdateCursor(fc_path, ["SHAPE@"]) as cursor:
        for row in cursor:
            cursor.deleteRow()
    print(f"Cleared existing records in {fc_name}.")

# Insert data into feature class
fields = ["SHAPE@", "CommonName", "Taxon", "Observer", "PercentCover"]

with arcpy.da.InsertCursor(fc_path, fields) as cursor:
    print(f"Total records fetched from API: {len(data)}")
    for record in data:
        print(f"Processing record: {record}")

        polygon = get_polygon_from_wkt(record)
        if not polygon:
            print(f"Skipping {record.get('Taxon', 'Unknown')} due to invalid geometry.")
            continue

        percent_cover = convert_percent_cover(record.get("Percent Cover", ""))
        print(f"Converted Percent Cover: {percent_cover}")
        print(f"Inserting {record.get('Taxon', '')} with percent cover {percent_cover}")

        cursor.insertRow([
            polygon,
            record.get("Common Name", ""),
            record.get("Taxon", ""),
            record.get("Observer", ""),
            percent_cover
        ])

print("Data added to feature class.")

# Apply symbology
symbology_layer = r'C:\GIS\CalfloraProject\Symbology.lyrx'

doc = arcpy.mp.ArcGISProject("CURRENT")
map_obj = doc.listMaps()[0]

# Check if layer already exists in the map
layer = None
for lyr in map_obj.listLayers():
    if lyr.name == fc_name:
        layer = lyr
        break

if layer is None:
    layer = map_obj.addDataFromPath(fc_path)
    print(f"Added {fc_name} layer to map.")
else:
    print(f"{fc_name} layer already exists in map.")

# Apply symbology from layer file
if os.path.exists(symbology_layer):
    layer.updateConnectionProperties(fc_path, fc_path)
    arcpy.ApplySymbologyFromLayer_management(layer, symbology_layer)
    print("Symbology applied.")
else:
    print(f"Symbology layer not found at {symbology_layer}")

# Export to PDF
pdf_output = r'C:\GIS\CalfloraProject\Calflora_Map.pdf'
layout = doc.listLayouts()[0]
layout.exportToPDF(pdf_output)
print(f"Map exported to {pdf_output}")
