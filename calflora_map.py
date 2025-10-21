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





##### SETUP WORKSPACE, GEODATABASE, FEATURE CLASS
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




###### DEFINE SEARCH PARAMETERS
    
# Define additional parameters for limiting the search
params = {
    'csetId': 291,
    #'shapeId': "rs1515",  # Example shapeId
    'shapeId': MGP_shapeID,

    #'plantlistId': plantlist_id,  # Example plantlistId
    #'projectIds': 'pr940',  # Example projectIds
}

# Define API endpoint with the species filter
#species = "Silybum marianum"
#api_url = f"https://api.calflora.org/observations?taxon={species.replace(' ', '%20')}&maxResults=10"

# Define API endpoint with the plant list filter
api_url = f"https://api.calflora.org/observations?plantlistId={plantlist_id}&maxResults=10"



###### API REQUEST AND RESPONSE
# Send the request with the additional parameters
headers = {"X-Api-Key": "insert key here"}
response = requests.get(api_url, headers=headers, params=params)

# Check the status and handle the response
if response.status_code == 200:
    data = response.json()
    print(f"Fetched {len(data)} records from the API.")
else:
    print("Error fetching data from API:", response.text)
    data = []


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
    # Check how many records are being processed
    print(f"Total records fetched from API: {len(data)}")
    
    for record in data:
        # Debug: Print the current record to see its contents
        print(f"Processing record: {record}")
        
        if "Reference Polygon" in record and record["Reference Polygon"]:
            wkt = record["Reference Polygon"]
            
            try:
                polygon = arcpy.FromWKT(wkt)
                print(f"Created polygon for {record['Taxon']}")
            except Exception as e:
                print(f"Error creating polygon: {e}")
                continue  # Skip this record if there's an error creating the polygon
            
            # Convert Percent Cover to a numeric value
            percent_cover = convert_percent_cover(record.get("Percent Cover", ""))
            
            # Debug: Print the converted percent cover value
            print(f"Converted Percent Cover: {percent_cover}")
            
            # Insert the row into the feature class with the percent cover (default if missing)
            print(f"Inserting {record['Taxon']} with percent cover {percent_cover}")
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
    layer.updateConnectionProperties(fc_path, fc_path)  # Ensures layer is properly linked
    arcpy.ApplySymbologyFromLayer_management(layer, symbology_layer)
    print("Symbology applied.")
else:
    print(f"Symbology layer not found at {symbology_layer}")



###### EXPORT 
# Export to PDF
pdf_output = r'C:\GIS\CalfloraProject\Calflora_Map.pdf'
layout = doc.listLayouts()[0]
layout.exportToPDF(pdf_output)
print(f"Map exported to {pdf_output}")