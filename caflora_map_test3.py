import arcpy
import requests
import os
from arcpy.da import InsertCursor, UpdateCursor

# -----------------------------
# SETTINGS
# -----------------------------
MGP_shapeID = "rs1515"
workspace = r'C:\GIS\CalfloraProject'
gdb_name = 'CalfloraData.gdb'
fc_name = "Calflora_Polygons"
symbology_layer = r'C:\GIS\CalfloraProject\Symbology.lyrx'
pdf_output = r'C:\GIS\CalfloraProject\Calflora_Map.pdf'
API_KEY = "CKLjKHH1nVZMlC8tsu"

# -----------------------------
# SETUP GEODATABASE & FEATURE CLASS
# -----------------------------
gdb_path = os.path.join(workspace, gdb_name)
fc_path = os.path.join(gdb_path, fc_name)

if not os.path.exists(workspace):
    os.makedirs(workspace)

if not arcpy.Exists(gdb_path):
    arcpy.CreateFileGDB_management(workspace, gdb_name)
    print(f"Created geodatabase: {gdb_path}")
else:
    print(f"Using existing geodatabase: {gdb_path}")

if not arcpy.Exists(fc_path):
    arcpy.CreateFeatureclass_management(gdb_path, fc_name, "POLYGON", spatial_reference=4326)
    arcpy.AddField_management(fc_path, "CommonName", "TEXT")
    arcpy.AddField_management(fc_path, "Taxon", "TEXT")
    arcpy.AddField_management(fc_path, "Observer", "TEXT")
    arcpy.AddField_management(fc_path, "PercentCover", "DOUBLE")
    print(f"Created feature class: {fc_path}")
else:
    print(f"Using existing feature class: {fc_path}")

# -----------------------------
# FUNCTION TO CONVERT PERCENT COVER
# -----------------------------
def convert_percent_cover(cover_value):
    if not cover_value:
        return 0
    cover_str = str(cover_value).strip()
    if " - " in cover_str:
        try:
            low, high = map(float, cover_str.split(" - "))
            return (low + high) / 2
        except:
            return 0
    try:
        return float(cover_str)
    except:
        return 0

# -----------------------------
# FETCH ALL API DATA WITH PAGINATION
# -----------------------------
api_url = "https://api.calflora.org/observations"
headers = {"X-Api-Key": API_KEY}

params = {
    'csetId': 291,
    'shapeId': MGP_shapeID,
    'projectIds': 'pr940',
    'maxResults': 100,  # max per page
    'startIndex': 0
}

all_data = []
while True:
    response = requests.get(api_url, headers=headers, params=params)
    if response.status_code != 200:
        print("Error fetching data:", response.text)
        break

    data = response.json()
    if not data:
        break

    all_data.extend(data)
    print(f"Fetched {len(data)} records, total so far: {len(all_data)}")

    if len(data) < params['maxResults']:
        break

    params['startIndex'] += params['maxResults']

print(f"Total records fetched from API: {len(all_data)}")

# -----------------------------
# CLEAR EXISTING FEATURE CLASS ROWS
# -----------------------------
with UpdateCursor(fc_path, ["SHAPE@"]) as cursor:
    for row in cursor:
        cursor.deleteRow()
print(f"Cleared existing records in {fc_name}.")

# -----------------------------
# INSERT RECORDS INTO FEATURE CLASS
# -----------------------------
fields = ["SHAPE@", "CommonName", "Taxon", "Observer", "PercentCover"]

with InsertCursor(fc_path, fields) as cursor:
    for record in all_data:
        wkt = record.get("Reference Polygon")
        if not wkt or not wkt.upper().startswith("POLYGON"):
            continue
        try:
            geom = arcpy.FromWKT(wkt)
        except Exception as e:
            print(f"Skipping {record.get('Taxon', 'Unknown')} due to WKT error: {e}")
            continue

        percent_cover = convert_percent_cover(record.get("Percent Cover", ""))
        cursor.insertRow([
            geom,
            record.get("Common Name", ""),
            record.get("Taxon", ""),
            record.get("Observer", ""),
            percent_cover
        ])

print("All records inserted into feature class.")

# -----------------------------
# APPLY SYMBOLOGY
# -----------------------------
doc = arcpy.mp.ArcGISProject("CURRENT")
map_obj = doc.listMaps()[0]

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

if os.path.exists(symbology_layer):
    arcpy.ApplySymbologyFromLayer_management(layer, symbology_layer)
    print("Symbology applied.")
else:
    print(f"Symbology layer not found at {symbology_layer}")

# -----------------------------
# EXPORT MAP TO PDF
# -----------------------------
layouts = doc.listLayouts()
if layouts:
    layouts[0].exportToPDF(pdf_output)
    print(f"Map exported to {pdf_output}")
else:
    print("No layout found. PDF export skipped.")
