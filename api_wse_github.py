#import arcpy
import requests
import pandas as pd
from pandas import json_normalize
#from arcpy import env
#from arcpy.da import InsertCursor
import sys
sys.path.append(r"C:\Users\henry.inman\OneDrive - Audubon Canyon Ranch\Documents 1\GitHub\calflora_maps")
#from config import API_KEY

#print(f"Using API key: '{API_KEY}'")


#### DEFINE PARAMATERS
dateAfter = "2023-01-01"
dateBefore = "2023-12-31"
projectId = "pr940"
#api_url = f"https://api.calflora.org/workSessions?dateAfter={dateAfter}&projectId={projectId}"
api_url = f"https://api.calflora.org/workSessions?dateAfter={dateAfter}&dateBefore={dateBefore}&projectId={projectId}"


##### API REQUEST FOR WSE

headers = {"X-Api-Key": "CKLjKHH1nVZMlC8tsu"}
response = requests.get(api_url, headers=headers)

# Check the status and handle the response
if response.status_code == 200:
    wse_data = response.json()
    df = pd.DataFrame(wse_data)
    print(f"Fetched {len(wse_data)} records from the API.")
    
else:
    print("Error fetching data from API:", response.text)
    wse_data = []

#print(df)
#print(df.columns)

##### CREATE LIST OF CALFLORA RECORDS BASED ON WSEs 


if not df.empty:
    cf_record_list = df["seq"].unique().tolist()
    print(f"Found{len(cf_record_list)} unique record IDs.")
else:
    cf_record_list = []




###### REQUEST FOR CALFLORA RECORDS FROM LIST


all_obs_data = []
for observationId in cf_record_list:
    api_url_2 = f"https://api.calflora.org/observations/{observationId}?includeGeometry=true&includeWorkSessions=true"
    obs_response = requests.get(api_url_2, headers=headers)

    if obs_response.status_code == 200:
        obs_data = obs_response.json()
        all_obs_data.append(obs_data)
    else:
        print(f"Failed to fetch record {observationId}: {obs_response.text}")

if all_obs_data:
    obs_df = json_normalize(all_obs_data)
    print(f"Fetched {len(obs_df)} observation records.")
else:
    print("No observation records were fetched.")

print("Test")
print(obs_df)


#### SETUP / WORKSPACE, GEODATABASE

##### SETUP WORKSPACE, GEODATABASE, FEATURE CLASS
# Define workspace and geodatabase

data = all_obs_data
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

###### CLEAN DATA
# Function to convert percent cover range to a numeric value (average of the range)
def convert_percent_cover(cover_str):
    if cover_str:
        # Extract numeric values from the string (e.g., "1 - 5" -> 1, 5)
        range_values = cover_str.split(" - ")
        if len(range_values) == 2:
            low = float(range_values[0])
            high = float(range_values[1])
            # Return the average of the range
            return (low + high) / 2
    # Return 0 (or another default value) if the string doesn't match a range
    return 0

# Delete all existing rows from the feature class to avoid accumulation of old data
if arcpy.Exists(fc_path):
    with arcpy.da.UpdateCursor(fc_path, ["SHAPE@"]) as cursor:
        for row in cursor:
            cursor.deleteRow()
    print(f"Cleared existing records in {fc_name}.")


##### INSERT DATA INTO FEATURE CLASS
# Insert data into feature class (for the most recent API call)
fields = ["SHAPE@", "CommonName", "Taxon", "Observer", "PercentCover"]

with arcpy.da.InsertCursor(fc_path, fields) as cursor:
    print(f"Total records fetched from API: {len(data)}")
    
    for record in data:
        print(f"Processing record: {record}")
        
        if "Geometry" in record and record["Geometry"]:
            wkt = record["Geometry"].strip()
            try:
                polygon = arcpy.FromWKT(wkt)
                print(f"Created polygon for {record['Taxon']}")
            except Exception as e:
                print(f"Error creating polygon: {e}")
                continue
            
            percent_cover = convert_percent_cover(record.get("Percent Cover", ""))
            cursor.insertRow([polygon, 
                              record.get("Common Name", ""), 
                              record.get("Taxon", ""), 
                              record.get("Observer", ""), 
                              percent_cover])
        else:
            print(f"Skipping {record['Taxon']} due to missing polygon data")


print("Data added to feature class.")

###### SYMBOLOGY 
# Apply symbology
symbology_layer = r'C:\GIS\CalfloraProject\Symbology_Species.lyrx'

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
    layer.updateConnectionProperties(fc_path, fc_path)  # Ensures layer is properly linked
    arcpy.ApplySymbologyFromLayer_management(layer, symbology_layer)
    print("Symbology applied.")
else:
    print(f"Symbology layer not found at {symbology_layer}")



###### EXPORT 
# Export to PDF

layouts = doc.listLayouts()
if layouts:
    layout = layouts[0]
    layout.exportToPDF(pdf_output)
    print(f"Map exported to {pdf_output}")
else:
    print("⚠ No layouts found in the ArcGIS Project. PDF export skipped.")