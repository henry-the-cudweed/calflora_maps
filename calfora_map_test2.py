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

# --------------------------
# Config / parameters
# --------------------------
API_KEY = "CKLjKHH1nVZMlC8tsu"   # <-- replace with your key (keep as string)
MGP_shapeID = "rs1515"
workspace = r'C:\GIS\CalfloraProject'
gdb_name = 'CalfloraData.gdb'
gdb_path = os.path.join(workspace, gdb_name)
fc_name = "Calflora_Polygons"
fc_path = os.path.join(gdb_path, fc_name)
symbology_layer = r'C:\GIS\CalfloraProject\Symbology.lyrx'
pdf_output = r'C:\GIS\CalfloraProject\Calflora_Map.pdf'
plantlist_id = 'px1436'

# Local projected CRS for buffering (UTM zone 10N - good for SF Bay Area)
projected_sr = arcpy.SpatialReference(26910)  # NAD83 / UTM zone 10N
wgs84_sr = arcpy.SpatialReference(4326)       # WGS84 (what you store in the GDB)

# --------------------------
# Ensure workspace & gdb
# --------------------------
if not os.path.exists(workspace):
    os.makedirs(workspace)

if not arcpy.Exists(gdb_path):
    arcpy.CreateFileGDB_management(workspace, gdb_name)
    print(f"Created geodatabase: {gdb_path}")
else:
    print(f"Using existing geodatabase: {gdb_path}")

# --------------------------
# Create feature class if missing
# --------------------------
if not arcpy.Exists(fc_path):
    # create as POLYGON in WGS84
    arcpy.CreateFeatureclass_management(gdb_path, fc_name, "POLYGON", spatial_reference=wgs84_sr)
    # Add fields (PercentCover as DOUBLE)
    arcpy.AddField_management(fc_path, "CommonName", "TEXT")
    arcpy.AddField_management(fc_path, "Taxon", "TEXT")
    arcpy.AddField_management(fc_path, "Observer", "TEXT")
    arcpy.AddField_management(fc_path, "PercentCover", "DOUBLE")
    print(f"Created feature class: {fc_path}")
else:
    print(f"Using existing feature class: {fc_path}")

# --------------------------
# Call API
# --------------------------
params = {
    'csetId': 291,
    'shapeId': MGP_shapeID
}
api_url = f"https://api.calflora.org/observations?plantlistId={plantlist_id}&maxResults=1000"

headers = {"X-Api-Key": API_KEY}
response = requests.get(api_url, headers=headers, params=params)

if response.status_code == 200:
    data = response.json()
    print(f"Fetched {len(data)} records from the API.")
else:
    print("Error fetching data from API:", response.text)
    data = []

# --------------------------
# Helpers
# --------------------------
def convert_percent_cover(value):
    """
    Accepts strings like '1 - 5', a single numeric string '3', numeric floats/ints,
    or None. Returns a float (0.0 if missing/invalid).
    """
    if value is None:
        return 0.0
    # numeric already
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return 0.0
    # string handling
    if isinstance(value, str):
        s = value.strip()
        # handle common variants
        s = s.replace('%', '')
        s = s.replace('–', '-')
        parts = [p.strip() for p in s.split('-') if p.strip() != ""]
        if len(parts) == 2:
            try:
                low = float(parts[0])
                high = float(parts[1])
                return (low + high) / 2.0
            except Exception:
                return 0.0
        else:
            # try single numeric
            try:
                return float(parts[0])
            except Exception:
                return 0.0
    return 0.0

def get_polygon_from_wkt(record, default_radius_m=3.0):
    """
    Given an API record with 'Reference Polygon' (WKT) and optional 'radius',
    return an arcpy Polygon geometry in WGS84 suitable for inserting into the
    polygon feature class. If impossible, return None.
    Implementation details:
      - POLYGON WKT -> arcpy.FromWKT and return
      - LINESTRING WKT -> create an in_memory line feature, project to UTM,
        buffer using arcpy.Buffer_analysis in meters, read first polygon from
        the buffer result, project back to WGS84, return that polygon.
    """
    wkt = record.get("Reference Polygon")
    if not wkt:
        return None

    wkt = wkt.strip()
    try:
        if wkt.upper().startswith("POLYGON"):
            # Direct polygon
            geom = arcpy.FromWKT(wkt)
            # ensure geometry is in WGS84 — if not, project
            try:
                # If geometry not in WGS84 (no sr), assume it's WGS84; otherwise project
                if geom.spatialReference is None:
                    geom = geom.projectAs(wgs84_sr)
                else:
                    geom = geom.projectAs(wgs84_sr)
            except Exception:
                # safe fallback: return geom as-is
                pass
            return geom

        elif wkt.upper().startswith("LINESTRING"):
            # Create an arcpy geometry from WKT
            line_geom = arcpy.FromWKT(wkt)

            # Determine radius: prefer 'radius' field; fall back to default_radius_m
            raw_radius = record.get("radius", None)
            radius_m = default_radius_m
            try:
                if raw_radius not in (None, ""):
                    radius_m = float(raw_radius)
            except Exception:
                radius_m = default_radius_m

            # Create in-memory line feature (overwrite if exists)
            temp_line_fc = "in_memory\\tmp_line"
            if arcpy.Exists(temp_line_fc):
                arcpy.Delete_management(temp_line_fc)
            # CopyFeatures accepts a geometry object in a list
            arcpy.CopyFeatures_management([line_geom], temp_line_fc)

            # Project the line to projected_sr for buffering in meters
            temp_line_proj = "in_memory\\tmp_line_prj"
            if arcpy.Exists(temp_line_proj):
                arcpy.Delete_management(temp_line_proj)
            arcpy.Project_management(temp_line_fc, temp_line_proj, projected_sr)

            # Buffer in meters using geoprocessing (distance string uses METERS)
            temp_buf = "in_memory\\tmp_buf"
            if arcpy.Exists(temp_buf):
                arcpy.Delete_management(temp_buf)
            arcpy.Buffer_analysis(temp_line_proj, temp_buf, f"{radius_m} METERS", dissolve_option="ALL")

            # Read the first polygon geometry from the buffer result
            polygon_geom = None
            with arcpy.da.SearchCursor(temp_buf, ["SHAPE@"]) as scur:
                for prow in scur:
                    polygon_geom = prow[0]
                    break  # use the first geometry (if multiple features created)

            # clean up temp in_memory layers
            try:
                if arcpy.Exists(temp_line_fc):
                    arcpy.Delete_management(temp_line_fc)
                if arcpy.Exists(temp_line_proj):
                    arcpy.Delete_management(temp_line_proj)
                if arcpy.Exists(temp_buf):
                    arcpy.Delete_management(temp_buf)
            except Exception:
                pass

            if polygon_geom is None:
                print("Buffer produced no polygon for LINESTRING.")
                return None

            # Project polygon back to WGS84 for storage
            try:
                polygon_wgs84 = polygon_geom.projectAs(wgs84_sr)
            except Exception:
                polygon_wgs84 = polygon_geom

            return polygon_wgs84

        else:
            print(f"Unsupported geometry WKT prefix: {wkt[:40]}")
            return None

    except Exception as e:
        print(f"Error in get_polygon_from_wkt: {e}")
        return None

# --------------------------
# Clear existing rows in FC
# --------------------------
if arcpy.Exists(fc_path):
    # Use UpdateCursor to delete all rows
    with arcpy.da.UpdateCursor(fc_path, ["OID@"]) as ucur:
        for _ in ucur:
            ucur.deleteRow()
    print(f"Cleared existing records in {fc_name}.")

# --------------------------
# Insert rows
# --------------------------
fields = ["SHAPE@", "CommonName", "Taxon", "Observer", "PercentCover"]

with arcpy.da.InsertCursor(fc_path, fields) as cursor:
    print(f"Total records fetched from API: {len(data)}")
    for record in data:
        print(f"Processing record ID/Taxon: {record.get('ID', 'n/a')} / {record.get('Taxon', 'n/a')}")
        poly = get_polygon_from_wkt(record)
        if poly is None:
            print(f"Skipping {record.get('Taxon','Unknown')} - no valid polygon geometry.")
            continue

        # convert percent cover robustly
        percent_cover = convert_percent_cover(record.get("Percent Cover", None))
        # Insert row. PercentCover is DOUBLE (if created); inserting Python float is fine.
        try:
            cursor.insertRow([
                poly,
                record.get("Common Name", ""),
                record.get("Taxon", ""),
                record.get("Observer", ""),
                float(percent_cover)
            ])
            print(f"Inserted {record.get('Taxon','Unknown')} with percent cover {percent_cover}")
        except Exception as e:
            print(f"Failed to insert row for {record.get('Taxon','Unknown')}: {e}")

print("Data added to feature class.")

# --------------------------
# Apply symbology and export
# --------------------------
try:
    aprx = arcpy.mp.ArcGISProject("CURRENT")
    map_obj = aprx.listMaps()[0]

    # find or add layer
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
        # Ensure connection properties — this call is safe when layer is a Layer object
        try:
            layer.updateConnectionProperties(fc_path, fc_path)
        except Exception:
            pass
        arcpy.ApplySymbologyFromLayer_management(layer, symbology_layer)
        print("Symbology applied.")
    else:
        print(f"Symbology layer not found at {symbology_layer}")

    # Export layout to PDF (use first layout)
    try:
        layout = aprx.listLayouts()[0]
        layout.exportToPDF(pdf_output)
        print(f"Map exported to {pdf_output}")
    except Exception as e:
        print(f"Export to PDF failed: {e}")

except Exception as e:
    print(f"Error applying symbology/exporting map: {e}")
