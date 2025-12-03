#!/usr/bin/env python
# coding: utf-8

# In[2]:


get_ipython().run_line_magic('pip', 'install osmnx networkx matplotlib -q')


# Import geo files for BC:

# In[ ]:


# --- Step 1: Download the ZIP File (Execute shell command using !) ---
print("Downloading NRN data...")
get_ipython().system('wget https://geo.statcan.gc.ca/nrn_rrn/bc/nrn_rrn_bc_GPKG.zip')

# --- Step 2: Unzip the contents ---
print("Unzipping file...")
get_ipython().system('unzip nrn_rrn_bc_GPKG.zip')

print("\nDownload and extraction complete. The file 'NRN_BC_14_0_GPKG_en.gpkg' is now ready to be processed by the Factory script.")


# Test for Langley, BC:

# In[1]:


import osmnx as ox
import networkx as nx
import matplotlib.pyplot as plt

# 1. Define the location and download the driving network
place = "Langley, British Columbia, Canada"
G = ox.graph_from_place(place, network_type="drive")

# 2. Impute missing speed data and calculate travel time for each road segment
# This is crucial for finding the *fastest* route, not just the shortest distance.
G = ox.add_edge_speeds(G)
G = ox.add_edge_travel_times(G)

print(f"Graph loaded for {place}.")
print(f"Number of nodes (intersections/dead-ends): {len(G.nodes)}")
print(f"Number of edges (road segments): {len(G.edges)}")


# Test to 2 nurses, 2 routes:

# In[3]:


import osmnx as ox
import networkx as nx

print("Starting OSMnx routing setup...")

# 1. Download the graph
place = "Langley, British Columbia, Canada"
# Note: In OSMnx 2.0+, 'network_type' is still valid, but ensure other params are correct.
G = ox.graph_from_place(place, network_type="drive")

print(f"Graph loaded. Nodes: {len(G.nodes)}, Edges: {len(G.edges)}")

# 2. FAIL-SAFE FILTERING (Using NetworkX directly)
# Instead of ox.get_largest_component, we use standard NetworkX commands.
# We find the largest 'strongly connected component' (nodes that can reach each other).
largest_cc_nodes = max(nx.strongly_connected_components(G), key=len)
G = G.subgraph(largest_cc_nodes).copy()

print(f"Graph filtered to largest connected component. Nodes remaining: {len(G.nodes)}")

# 3. Add Speeds and Travel Times
G = ox.add_edge_speeds(G)
G = ox.add_edge_travel_times(G)

# 4. Define Mock Routes (Revised Coordinates on Main Roads)
# Nurse A: Langley City Hall -> Willowbrook Mall
orig_lat1, orig_lon1 = 49.1042, -122.6604 
dest_lat1, dest_lon1 = 49.1258, -122.6713 

# Nurse B: Walnut Grove -> Fort Langley
orig_lat2, orig_lon2 = 49.1670, -122.6390 
dest_lat2, dest_lon2 = 49.1678, -122.5780 

# 5. Route Analysis Function
def analyze_route(G, orig_lat, orig_lon, dest_lat, dest_lon, route_name):
    # Find nearest nodes
    orig_node = ox.nearest_nodes(G, orig_lon, orig_lat)
    dest_node = ox.nearest_nodes(G, dest_lon, dest_lat)

    # Calculate shortest path
    # Note: If ox.shortest_path fails in v2.0, use nx.shortest_path directly
    try:
        route = ox.shortest_path(G, orig_node, dest_node, weight="travel_time")
    except AttributeError:
        # Fallback for very new versions if top-level alias is missing
        route = nx.shortest_path(G, orig_node, dest_node, weight="travel_time")

    if route is None:
        print(f"{route_name}: ERROR - No path found.")
        return

    # Calculate Distance and Time Manually (Version Agnostic)
    total_len = 0
    total_time = 0
    for u, v in zip(route[:-1], route[1:]):
        # Handle MultiDiGraph edges (get the one with min travel_time)
        edge_data = G.get_edge_data(u, v)
        if edge_data:
            # If multiple edges exist, pick the one with lowest travel time
            best_key = min(edge_data, key=lambda k: edge_data[k].get('travel_time', float('inf')))
            attr = edge_data[best_key]
            total_len += attr.get('length', 0)
            total_time += attr.get('travel_time', 0)

    print(f"\n--- {route_name} ---")
    print(f"Total Distance: {total_len/1000:.2f} km")
    print(f"Est. Travel Time: {total_time/60:.1f} min")

# Run Analysis
analyze_route(G, orig_lat1, orig_lon1, dest_lat1, dest_lon1, "Nurse A (City Trip)")
analyze_route(G, orig_lat2, orig_lon2, dest_lat2, dest_lon2, "Nurse B (Township Trip)")


# Test for more nurses and routes:

# In[5]:


# Assuming G (the Langley graph) is already loaded and processed
print("\n--- Batch Processing 100 Trips ---")

# Step 1: Extract all Origin and Destination Coordinates
# OSMnx nearest_nodes expects LONGITUDE first, then LATITUDE
orig_lons = trips_df['orig_lon'].values
orig_lats = trips_df['orig_lat'].values
dest_lons = trips_df['dest_lon'].values
dest_lats = trips_df['dest_lat'].values

# Step 2: Batch Find Nearest Nodes
# This is much faster than looping!
trips_df['orig_node'] = ox.nearest_nodes(G, orig_lons, orig_lats)
trips_df['dest_node'] = ox.nearest_nodes(G, dest_lons, dest_lats)

# Step 3: Loop and Calculate Path
# The shortest_path calculation still needs to be done in a loop, but
# using the pre-calculated nodes makes it significantly faster.
results = []
for index, row in trips_df.iterrows():
    orig_node = row['orig_node']
    dest_node = row['dest_node']

    # Calculate shortest path
    route = ox.shortest_path(G, orig_node, dest_node, weight="travel_time")

    total_time = np.nan
    total_distance = np.nan

    if route is not None:
        # Calculate Distance and Time by summing edge attributes
        route_stats = []
        for u, v in zip(route[:-1], route[1:]):
            edge_data = G.get_edge_data(u, v)
            if edge_data:
                # Find the best edge attributes
                best_key = min(edge_data, key=lambda k: edge_data[k].get('travel_time', float('inf')))
                attr = edge_data[best_key]
                route_stats.append((attr.get('length', 0), attr.get('travel_time', 0)))

        if route_stats:
            lengths, times = zip(*route_stats)
            total_distance = sum(lengths) / 1000  # km
            total_time = sum(times) / 60         # minutes

    results.append({
        'trip_id': row['trip_id'],
        'distance_km': total_distance,
        'travel_time_min': total_time
    })

# Convert results to a DataFrame and merge
results_df = pd.DataFrame(results)
final_trips_df = trips_df.merge(results_df, on='trip_id')

print("\n--- Final Batched Results (First 5 Trips) ---")
print(final_trips_df[['trip_id', 'nurse_id', 'distance_km', 'travel_time_min']].head())


# Mock 1,000 trips for Langley, BC:

# In[6]:


import pandas as pd
import numpy as np
import osmnx as ox
import networkx as nx
from multiprocessing import Pool, cpu_count
import itertools

# Create a mock DataFrame of 1000 trips
center_lat, center_lon = 49.10, -122.65
num_trips = 1000 

np.random.seed(42)
data = {
    'trip_id': range(num_trips),
    'orig_lat': center_lat + np.random.uniform(-0.05, 0.05, num_trips),
    'orig_lon': center_lon + np.random.uniform(-0.08, 0.08, num_trips),
    'dest_lat': center_lat + np.random.uniform(-0.05, 0.05, num_trips),
    'dest_lon': center_lon + np.random.uniform(-0.08, 0.08, num_trips)
}
trips_df = pd.DataFrame(data)

# Find Nearest Nodes (Still done efficiently in one batch)
orig_lons = trips_df['orig_lon'].values
orig_lats = trips_df['orig_lat'].values
dest_lons = trips_df['dest_lon'].values
dest_lats = trips_df['dest_lat'].values

# Assuming G is the pre-loaded, filtered, and processed Langley graph
# (Graph loading steps are omitted here for brevity)
trips_df['orig_node'] = ox.nearest_nodes(G, orig_lons, orig_lats)
trips_df['dest_node'] = ox.nearest_nodes(G, dest_lons, dest_lats)

print(f"Set up {num_trips} origin/destination pairs.")


# In[8]:


import pandas as pd
import numpy as np
import osmnx as ox
import networkx as nx

# --- 1. Setup Graph (Langley) ---
print("Setting up graph...")
place = "Langley, British Columbia, Canada"
G = ox.graph_from_place(place, network_type="drive")

# Filter to largest component (Standard NetworkX method)
largest_cc = max(nx.strongly_connected_components(G), key=len)
G = G.subgraph(largest_cc).copy()

# Add speeds/times
G = ox.add_edge_speeds(G)
G = ox.add_edge_travel_times(G)
print(f"Graph ready: {len(G.nodes)} nodes.")

# --- 2. Generate 1,000 Mock Trips ---
print("Generating 1,000 mock trips...")
center_lat, center_lon = 49.10, -122.65
num_trips = 1000 
np.random.seed(42)

trips_df = pd.DataFrame({
    'trip_id': range(num_trips),
    'orig_lat': center_lat + np.random.uniform(-0.05, 0.05, num_trips),
    'orig_lon': center_lon + np.random.uniform(-0.08, 0.08, num_trips),
    'dest_lat': center_lat + np.random.uniform(-0.05, 0.05, num_trips),
    'dest_lon': center_lon + np.random.uniform(-0.08, 0.08, num_trips)
})

# --- 3. Batch Processing (The Fix) ---

# A. Find all nearest nodes at once
# Pass the entire arrays of lons and lats. This is extremely fast.
trips_df['orig_node'] = ox.nearest_nodes(G, trips_df['orig_lon'], trips_df['orig_lat'])
trips_df['dest_node'] = ox.nearest_nodes(G, trips_df['dest_lon'], trips_df['dest_lat'])

# B. Calculate all 1,000 routes at once
# You can pass the columns (Series) directly to shortest_path.
print("Calculating 1,000 shortest paths...")
routes = ox.shortest_path(G, trips_df['orig_node'], trips_df['dest_node'], weight='travel_time')

# --- 4. Process Results ---
# 'routes' is now a list of 1000 paths (or None if no path found).
# We quickly iterate through them to sum up the distances/times.

distances_km = []
times_min = []

for route in routes:
    if route is None:
        distances_km.append(np.nan)
        times_min.append(np.nan)
    else:
        # Sum edge attributes for the path
        # Using a list comprehension for speed
        edge_data_list = [G.get_edge_data(u, v) for u, v in zip(route[:-1], route[1:])]

        # Handle cases where edge_data might be missing or complex (MultiDiGraph)
        # We take the first available edge key (0) for simplicity in this batch
        d = sum(d[0]['length'] for d in edge_data_list)
        t = sum(d[0]['travel_time'] for d in edge_data_list)

        distances_km.append(d / 1000)
        times_min.append(t / 60)

# Add results back to DataFrame
trips_df['distance_km'] = distances_km
trips_df['travel_time_min'] = times_min

print("\n--- Processing Complete ---")
print(f"Successfully calculated {trips_df['distance_km'].notna().sum()} routes.")
print(trips_df[['trip_id', 'distance_km', 'travel_time_min']].head(10))


# In[11]:


print(trips_df[['trip_id', 'distance_km', 'travel_time_min']].tail(10))


# Load a section of BC geo data to **local storage**

# In[1]:


import geopandas as gpd
import osmnx as ox
import networkx as nx
import pandas as pd
import numpy as np
from shapely.geometry import Point

# --- 1. Load Data (Keep your existing Step 1) ---
gpkg_filename = "NRN_BC_14_0_GPKG_en.gpkg"
layer_name = "NRN_BC_14_0_ROADSEG"
print("1. Loading Data...")
gdf_roads = gpd.read_file(gpkg_filename, layer=layer_name)

# --- 2. Build Topology (Vectorized) ---
print("2. Building Topology...")

# Round coordinates to snap connections
gdf_roads['u_coord'] = gdf_roads.geometry.apply(lambda x: (round(x.coords[0][0], 6), round(x.coords[0][1], 6)))
gdf_roads['v_coord'] = gdf_roads.geometry.apply(lambda x: (round(x.coords[-1][0], 6), round(x.coords[-1][1], 6)))

# Map unique coordinates to IDs
all_nodes = pd.concat([gdf_roads['u_coord'], gdf_roads['v_coord']]).unique()
node_map = {coord: i for i, coord in enumerate(all_nodes)}

gdf_roads['u'] = gdf_roads['u_coord'].map(node_map)
gdf_roads['v'] = gdf_roads['v_coord'].map(node_map)

# Handle Parallel Edges (The "Unique Index" Fix)
gdf_roads['key'] = gdf_roads.groupby(['u', 'v']).cumcount()

# Create Nodes GDF
print(f"   Nodes: {len(all_nodes):,}")
node_rows = [{'osmid': i, 'geometry': Point(coord), 'x': coord[0], 'y': coord[1]} 
             for coord, i in node_map.items()]
gdf_nodes = gpd.GeoDataFrame(node_rows, crs=gdf_roads.crs).set_index('osmid')

# --- 3. Calculate Speed & Time (Vectorized - NO LOOPS) ---
print("3. Calculating Metrics in Pandas (High Performance)...")

# A. Define Fallback Speeds (if 'SPEED' column is 0 or NaN)
# Mappings based on 'ROADCLASS' column
class_speeds = {
    'Freeway': 100, 'Expressway': 90, 'Arterial': 60, 
    'Collector': 50, 'Local': 40, 'Resource': 30, 'Ferry': 10
}
# Map the class to a temporary speed column
fallback_speeds = gdf_roads['ROADCLASS'].map(class_speeds).fillna(30)

# B. Determine Base Speed
# Use provided 'SPEED' column first. If 0 or NaN, use fallback.
gdf_roads['speed_kph'] = gdf_roads['SPEED'].replace(0, np.nan)
gdf_roads['speed_kph'] = gdf_roads['speed_kph'].fillna(fallback_speeds)

# C. Apply Surface Penalty (PAVSURF)
# If PAVSURF is not 'Paved' (e.g. 'Loose', 'Rough'), multiply by 0.6
gdf_roads['surface_penalty'] = np.where(gdf_roads['PAVSURF'].isin(['Paved', 'Concrete', 'Asphalt']), 1.0, 0.6)
gdf_roads['speed_kph'] = gdf_roads['speed_kph'] * gdf_roads['surface_penalty']

# D. Calculate Travel Time (Minutes)
# Length is in meters. (Meters / 1000) / KPH * 60 = Minutes
gdf_roads['travel_time'] = (gdf_roads.geometry.length / 1000 / gdf_roads['speed_kph']) * 60

# E. Add Ferry Penalty
# If ROADCLASS is Ferry, add 30 mins
gdf_roads.loc[gdf_roads['ROADCLASS'] == 'Ferry', 'travel_time'] += 30

print("   Metrics calculated.")

# --- 4. Create Graph ---
print("4. Creating Graph...")
# Set index required by OSMnx
gdf_roads = gdf_roads.set_index(['u', 'v', 'key'])

# Verify uniqueness
assert gdf_roads.index.is_unique, "Edge index is not unique!"
assert gdf_nodes.index.is_unique, "Node index is not unique!"

# Create Graph
G_BC = ox.graph_from_gdfs(gdf_nodes, gdf_roads)

# --- 5. Save ---
outfile = "BC_NRN_MASTER.graphml"
print(f"5. Saving to {outfile}...")
ox.save_graphml(G_BC, filepath=outfile)

print(f"✅ SUCCESS! Graph saved. Nodes: {len(G_BC.nodes):,}, Edges: {len(G_BC.edges):,}")


# In[2]:


import osmnx as ox
import pandas as pd

# Load and Project
G = ox.load_graphml("BC_NRN_MASTER.graphml")
G_proj = ox.project_graph(G)

# Check Coordinates
node_x = [G_proj.nodes[n]['x'] for n in list(G_proj.nodes)[:5]]
node_y = [G_proj.nodes[n]['y'] for n in list(G_proj.nodes)[:5]]

print("--- DEBUG REPORT ---")
print(f"Graph CRS: {G_proj.graph['crs']}")
print(f"Sample Graph Node X (Meters): {node_x[0]:.1f}")
print(f"Sample Trip Input X (Degrees): -123.0")
print(f"DIFFERENCE: {abs(node_x[0] - (-123)):,.0f} units!")
print("Result: Inputs are ~500km away from the graph's coordinate system.")


# 🏭 The "No-Compromise" Factory Script

# In[4]:


import osmnx as ox
import networkx as nx
import geopandas as gpd
import pandas as pd
import numpy as np
import gc
import psutil
import os
from shapely.geometry import Point

print("🏁 FACTORY v5.1 (Sanitized & Adjusted) STARTING...")

def get_ram():
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

print(f"   Initial RAM: {get_ram():.1f} MB")

# --- 1. Load Raw Data with GeoPandas ---
print("1. Loading & Sanitizing NRN Data...")
gpkg_filename = "NRN_BC_14_0_GPKG_en.gpkg"
layer_name = "NRN_BC_14_0_ROADSEG"

try:
    gdf_roads = gpd.read_file(gpkg_filename, layer=layer_name)
except Exception as e:
    print(f"❌ Error loading file: {e}")
    print("   Ensure 'NRN_BC_14_0_GPKG_en.gpkg' is in the current directory.")
    exit()

initial_len = len(gdf_roads)

# --- SANITIZATION STEP ---
print("   Sanitizing geometry and attributes...")
# A. Remove Empty/Null Geometries (Fixes "Null Island" artifacts)
gdf_roads = gdf_roads[gdf_roads.geometry.notna() & gdf_roads.geometry.is_valid]

# B. FILTER MASSIVE ARTIFACTS (Adjusted Threshold)
# User Correction: Valid roads can be up to ~140km.
# "Null Island" artifacts are > 5000km.
# Threshold: 2.0 degrees is approx 220km (Lat) to 140km (Lon at 50N).
# This safely preserves long highways while deleting the global errors.
gdf_roads = gdf_roads[gdf_roads.geometry.length < 2.0]

# C. Remove tiny artifacts (less than 1 meter)
gdf_roads = gdf_roads[gdf_roads.geometry.length > 0.00001] 

# D. SPATIAL FILTER (Secondary Safety Net)
# Strictly keep data within BC bounding box
print("   Applying Spatial Filter...")
gdf_roads = gdf_roads.cx[-140:-110, 48:62]

# E. Fix Negative Speeds
# Replace -1 (Unknown) with 50 km/h default
gdf_roads['SPEED'] = gdf_roads['SPEED'].replace(-1, 50)
gdf_roads['SPEED'] = gdf_roads['SPEED'].replace(0, 50) 
# Force numeric to prevent string errors
gdf_roads['SPEED'] = pd.to_numeric(gdf_roads['SPEED'], errors='coerce').fillna(50)

print(f"   Dropped {initial_len - len(gdf_roads)} bad rows.")

# --- 2. Build Topology (Vectorized) ---
print("2. Building Topology...")
# Rounding coordinates prevents micro-gaps (floating point errors)
gdf_roads['u_coord'] = gdf_roads.geometry.apply(lambda x: (round(x.coords[0][0], 6), round(x.coords[0][1], 6)))
gdf_roads['v_coord'] = gdf_roads.geometry.apply(lambda x: (round(x.coords[-1][0], 6), round(x.coords[-1][1], 6)))

# Map IDs
all_nodes = pd.concat([gdf_roads['u_coord'], gdf_roads['v_coord']]).unique()
node_map = {coord: i for i, coord in enumerate(all_nodes)}

gdf_roads['u'] = gdf_roads['u_coord'].map(node_map)
gdf_roads['v'] = gdf_roads['v_coord'].map(node_map)
# Handle parallel edges by assigning unique keys
gdf_roads['key'] = gdf_roads.groupby(['u', 'v']).cumcount()

# Create Nodes GDF
node_rows = [{'osmid': i, 'geometry': Point(coord), 'x': coord[0], 'y': coord[1]} for coord, i in node_map.items()]
gdf_nodes = gpd.GeoDataFrame(node_rows, crs=gdf_roads.crs).set_index('osmid')
gdf_roads = gdf_roads.set_index(['u', 'v', 'key'])

# --- 3. Create Graph ---
print("3. Converting to NetworkX Graph...")
G = ox.graph_from_gdfs(gdf_nodes, gdf_roads)

# Memory Cleanup
del gdf_nodes, gdf_roads, node_rows, node_map
gc.collect()

# --- 4. Repair & Project ---
print("4. Repairing & Projecting (Bidirectional)...")
# Make bidirectional so routing works in both directions
G = G.to_undirected()
G = G.to_directed()

# Project to UTM (Meters)
G_proj = ox.project_graph(G)
del G
gc.collect()

# Consolidate intersections to fix "spaghetti" topology
print("   Consolidating intersections (15m tolerance)...")
G_fixed = ox.consolidate_intersections(G_proj, tolerance=15, rebuild_graph=True, dead_ends=False)
del G_proj
gc.collect()

# --- 5. Flatten & Calculate Physics ---
print("5. Flattening Graph & Calculating Physics...")
best_edges = {}
count_total = 0
count_kept = 0

for u, v, k, data in G_fixed.edges(keys=True, data=True):
    count_total += 1

    # Geometry Check
    if 'geometry' in data:
        length = data['geometry'].length
        geom = data['geometry']
    else:
        length = data.get('length', 0)
        geom = None

    # Speed Logic
    raw_speed = data.get('SPEED', 50) 
    speed = float(raw_speed)

    # Surface Penalty (Gravel is slower)
    surface = data.get('PAVSURF', 'Paved')
    if surface not in ['Paved', 'Concrete', 'Asphalt']:
        speed *= 0.6

    # Ferry Penalty
    if data.get('ROADCLASS') == 'Ferry':
        speed = 10 

    # Safety floor
    if speed < 1: speed = 10 

    # Calculate Time (Minutes)
    time_min = ((length / 1000) / speed) * 60

    # Ferry Fixed Wait Time Penalty
    if data.get('ROADCLASS') == 'Ferry':
        time_min += 30

    edge_attributes = {
        'length': length,
        'travel_time': time_min,
        'speed_kph': speed,
        'geometry': geom 
    }

    # Keep Fastest Edge (Flattening Logic)
    if (u, v) in best_edges:
        if time_min < best_edges[(u, v)]['travel_time']:
            best_edges[(u, v)] = edge_attributes
    else:
        best_edges[(u, v)] = edge_attributes
        count_kept += 1

print(f"   Reduced edges from {count_total} to {count_kept}.")

# --- 6. Save ---
print("6. Saving Cleaned Golden Graph...")
# We use MultiDiGraph container to satisfy OSMnx save requirements,
# but the data is topologically flat (one edge per pair).
G_flat = nx.MultiDiGraph() 
G_flat.add_nodes_from(G_fixed.nodes(data=True))
G_flat.add_edges_from((u, v, data) for (u, v), data in best_edges.items())
G_flat.graph['crs'] = G_fixed.graph['crs']

outfile = "BC_GOLDEN_CLEAN.graphml"
ox.save_graphml(G_flat, filepath=outfile)

print("-" * 40)
print(f"✅ DONE. Sanitized graph saved to: {outfile}")
print("-" * 40)


# Analyze the data, repair any issues: Graph Biopsy 

# In[8]:


import osmnx as ox
import networkx as nx
import pandas as pd
import numpy as np

GRAPH_FILE = "BC_GOLDEN_CLEAN.graphml"

print(f"🕵️ GRAPH BIOPSY: {GRAPH_FILE}")
print("-" * 50)

# 1. Load
try:
    G = ox.load_graphml(GRAPH_FILE)
    print(f"✅ Graph Loaded.")
    print(f"   Nodes: {len(G.nodes):,}")
    print(f"   Edges: {len(G.edges):,}")
    print(f"   CRS: {G.graph.get('crs', 'Unknown')}")
except Exception as e:
    print(f"❌ FATAL: Could not load graph. {e}")
    exit()

# 2. Check Coordinate System (The "Null Island" Check)
print("\n[1/3] COORDINATE BOUNDS CHECK")
x_vals = [d['x'] for n, d in G.nodes(data=True)]
y_vals = [d['y'] for n, d in G.nodes(data=True)]

min_x, max_x = min(x_vals), max(x_vals)
min_y, max_y = min(y_vals), max(y_vals)

print(f"   X Range: {min_x:,.1f} to {max_x:,.1f}")
print(f"   Y Range: {min_y:,.1f} to {max_y:,.1f}")

# Logic check for UTM Zone 10N (BC)
# BC is approx X: 200,000-800,000, Y: 5,300,000-6,600,000
if min_y < 1000:
    print("   🚨 FAIL: Nodes found near Y=0 (Null Island artifacts present!)")
elif min_y > 4000000 and max_y < 8000000:
    print("   ✅ PASS: Y-coordinates look like valid UTM Meters.")
else:
    print("   ⚠️ WARNING: Coordinates look suspicious. Check CRS.")

# 3. Check Edge Attributes (The "500k km" Check)
print("\n[2/3] EDGE PHYSICS CHECK")
edges = []
for u, v, data in G.edges(data=True):
    edges.append({
        'length': data.get('length', np.nan),
        'travel_time': data.get('travel_time', np.nan),
        'speed_kph': data.get('speed_kph', np.nan)
    })

df = pd.DataFrame(edges)
print(df.describe().round(4))

# Logic Check for Units
max_len = df['length'].max()
if max_len < 10:
    print("\n   🚨 FAIL: Max edge length is < 10.")
    print("      This implies units are DEGREES (0.001), not METERS.")
    print("      Routing math will interpret 0.001 meters as 'instant teleportation'.")
elif max_len > 500000:
    print(f"\n   🚨 FAIL: Max edge length is {max_len:,.0f} meters (500km+).")
    print("      This implies 'Ghost Lines' traversing the province.")
else:
    print(f"\n   ✅ PASS: Max edge is {max_len:,.0f}m. Units look like Meters.")

# 4. Sample Data
print("\n[3/3] SAMPLE EDGE DATA")
# Get a random edge
u, v, data = list(G.edges(data=True))[0]
print(f"   Edge {u} -> {v}:")
for k, val in data.items():
    print(f"     - {k}: {val} ({type(val).__name__})")


# Troip biopsy:

# In[9]:


import geopandas as gpd
import pandas as pd
import numpy as np
import osmnx as ox

GRAPH_FILE = "BC_GOLDEN_CLEAN.graphml"
TOTAL_TRIPS = 5

print(f"🕵️ MOCK DATA BIOPSY")
print("-" * 50)

# 1. Load Graph Metadata
G = ox.load_graphml(GRAPH_FILE)
target_crs = G.graph.get('crs')
print(f"   Graph CRS: {target_crs}")

# 2. Generate Raw Lat/Lon (Exact logic from production)
print("\n[1/2] GENERATING RAW LAT/LON...")
np.random.seed(42)
# Bounds: Squamish to Hope to Border
north, south = 50.75, 49.05
east, west = -121.35, -123.25

lats = np.random.uniform(south, north, TOTAL_TRIPS)
lons = np.random.uniform(east, west, TOTAL_TRIPS)

print(f"   Generated {TOTAL_TRIPS} points.")
print(f"   Sample 0: {lats[0]:.4f}, {lons[0]:.4f}")

# Check validity
if (48 < lats[0] < 60) and (-140 < lons[0] < -110):
    print("   ✅ PASS: Raw Lat/Lon is inside British Columbia.")
else:
    print("   🚨 FAIL: Raw coordinates are outside BC!")

# 3. Project to UTM (The "Match" Check)
print("\n[2/2] PROJECTING TO GRAPH CRS...")
gdf = gpd.GeoDataFrame(geometry=gpd.points_from_xy(lons, lats), crs="EPSG:4326")

try:
    gdf_proj = gdf.to_crs(target_crs)
    print("   ✅ Projection Successful.")

    # Check X/Y values
    sample_x = gdf_proj.geometry.x[0]
    sample_y = gdf_proj.geometry.y[0]

    print(f"   Sample 0 Projected: X={sample_x:,.1f}, Y={sample_y:,.1f}")

    # Load graph nodes to compare bounds
    node_x = [d['x'] for n, d in G.nodes(data=True)]
    node_y = [d['y'] for n, d in G.nodes(data=True)]

    g_min_x, g_max_x = min(node_x), max(node_x)
    g_min_y, g_max_y = min(node_y), max(node_y)

    print(f"   Graph Bounds: X [{g_min_x:,.0f} - {g_max_x:,.0f}], Y [{g_min_y:,.0f} - {g_max_y:,.0f}]")

    if (g_min_x < sample_x < g_max_x) and (g_min_y < sample_y < g_max_y):
        print("   ✅ PASS: Projected trip falls INSIDE the graph bounds.")
    else:
        print("   🚨 FAIL: Projected trip is OUTSIDE the graph bounds.")
        print("      (Snapping will pull this point to the edge, potentially causing errors)")

except Exception as e:
    print(f"   🚨 FAIL: Projection crashed. {e}")


# Graph repair:

# In[12]:


import osmnx as ox
import networkx as nx
import pandas as pd
import geopandas as gpd
import numpy as np
import gc

INPUT_FILE = "BC_GOLDEN_CLEAN.graphml"
OUTPUT_FILE = "BC_GOLDEN_REPAIRED.graphml"

print("🚑 STARTING GRAPH SURGERY (With Deep Inspection)...")

# 1. Load the "Confused" Graph
print("1. Loading Graph...")
G = ox.load_graphml(INPUT_FILE)
print(f"   Nodes: {len(G.nodes):,}")
print(f"   Edges: {len(G.edges):,}")

# --- NEW: PRE-OP BIOPSY (Inspect Formats & Data) ---
print("\n🔍 PRE-OP BIOPSY: Inspecting Input Data...")

# A. Check Coordinate Bounds
node_x = [d['x'] for n, d in G.nodes(data=True)]
node_y = [d['y'] for n, d in G.nodes(data=True)]
print(f"   Bounds X: {min(node_x):.1f} to {max(node_x):.1f}")
print(f"   Bounds Y: {min(node_y):.1f} to {max(node_y):.1f}")
if min(node_y) < 1000:
    print("   🚨 DIAGNOSIS: Graph contains 'Null Island' artifacts (Y near 0).")

# B. Check Sample Edge Formats
print("   Sample Edge Attributes:")
if len(G.edges) > 0:
    u, v, data = list(G.edges(data=True))[0]
    for k, val in data.items():
        print(f"     - {k}: {val} (Type: {type(val).__name__})")

# C. Check Edge Physics (The Smoking Gun)
lengths = [d.get('length', 0) for u, v, d in G.edges(data=True)]
print(f"   Max Edge Length: {max(lengths):.4f}")
if max(lengths) < 10:
    print("   🚨 DIAGNOSIS: Lengths are in DEGREES (<10), not METERS.")
elif max(lengths) > 500000:
    print("   🚨 DIAGNOSIS: Lengths are MASSIVE (>500km). Artifacts present.")

print("-" * 30)

# 2. SEPARATE & FIX COORDINATE SYSTEMS
print("\n2. Aligning Coordinate Systems...")
# Extract Nodes and Edges as GeoDataFrames
gdf_nodes, gdf_edges = ox.graph_to_gdfs(G)

# DIAGNOSIS: 
# Nodes are likely correct (UTM Meters: ~900,000)
# Edges are corrupted (Lat/Lon Degrees: ~-120) based on your logs.

# A. Fix Edges (Force Lat/Lon interpretation, then Project)
print("   Fixing Edge Geometries (Degrees -> Meters)...")
# We override the metadata to admit the geometry is actually EPSG:4326 (Lat/Lon)
gdf_edges = gdf_edges.set_crs("EPSG:4326", allow_override=True)
# Now we project them properly to UTM Zone 10N (Meters)
gdf_edges = gdf_edges.to_crs("EPSG:32610")

# B. Ensure Nodes are EPSG:32610 (They should be already)
if gdf_nodes.crs != "EPSG:32610":
    gdf_nodes = gdf_nodes.to_crs("EPSG:32610")

# 3. REBUILD GRAPH
print("3. Rebuilding Graph with Aligned Data...")
G_proj = ox.graph_from_gdfs(gdf_nodes, gdf_edges)
del gdf_nodes, gdf_edges, G
gc.collect()

# 4. FILTER ARTIFACTS & UPDATE PHYSICS
print("4. Updating Physics & Removing Artifacts...")
edges_to_remove = []
count_repaired = 0

# Threshold: 200km (200,000 meters)
# This keeps long highways (140km) but deletes Null Island rays (5000km+)
LENGTH_THRESHOLD = 200000

for u, v, k, data in G_proj.edges(keys=True, data=True):
    # Recalculate Length from the NOW CORRECTED geometry
    if 'geometry' in data:
        real_length = data['geometry'].length
    else:
        # Fallback (should not happen with GDF rebuild)
        real_length = data.get('length', 0)

    # FILTER: Remove if > 200km
    if real_length > LENGTH_THRESHOLD:
        edges_to_remove.append((u, v, k))
        continue

    # UPDATE ATTRIBUTES
    data['length'] = real_length

    # Recalculate Time
    # Ensure speed is float
    try:
        speed = float(data.get('speed_kph', 50))
    except (ValueError, TypeError):
        speed = 50.0

    if speed < 1: speed = 50.0

    # Time (min) = (Dist (km) / Speed (km/h)) * 60
    data['travel_time'] = ((real_length / 1000) / speed) * 60

    count_repaired += 1

# Delete the bad edges
if len(edges_to_remove) > 0:
    print(f"   ✂️ Cutting {len(edges_to_remove)} monster edges...")
    G_proj.remove_edges_from(edges_to_remove)

print(f"   Updated physics for {count_repaired:,} edges.")

# 5. SANITY CHECK
lengths = [d['length'] for u, v, d in G_proj.edges(data=True)]
max_len = max(lengths) if lengths else 0
avg_len = np.mean(lengths) if lengths else 0

print(f"   New Max Length: {max_len:,.1f} meters")
print(f"   New Avg Length: {avg_len:,.1f} meters")

if max_len < 10:
    print("   ⚠️ WARNING: Max length is tiny. Projection might still be wrong.")
elif max_len > 500000:
    print("   ⚠️ WARNING: Max length is huge. Artifacts persist.")
else:
    print("   ✅ SUCCESS: Edge lengths look realistic.")

# 6. Save
print(f"5. Saving Repaired Graph to {OUTPUT_FILE}...")
ox.save_graphml(G_proj, filepath=OUTPUT_FILE)
print("✅ REPAIR COMPLETE.")


# Production simulation:

# In[ ]:


import osmnx as ox
import networkx as nx
import pandas as pd
import geopandas as gpd
import numpy as np
import time
import gc
import psutil
import os
import sys
import matplotlib.pyplot as plt
from multiprocessing import Pool, cpu_count

# --- Configuration ---
CHUNK_SIZE = 100        # Frequent updates for smoother progress bar
TOTAL_TRIPS = 1000      # 1,000 trips
GRAPH_FILE = "BC_GOLDEN_REPAIRED.graphml" # Loading the repaired file
NUM_CORES = 8          

print(f"🏁 PRODUCTION START. RAM: {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MB")

# --- 1. Load Optimized Graph ---
print("1. Loading Golden Graph...")
# OSMnx loads as MultiDiGraph
G_multi = ox.load_graphml(GRAPH_FILE)
target_crs = G_multi.graph['crs']

# Flatten to DiGraph for High-Speed Routing
# This enables O(1) attribute lookup and prevents plotting errors
G = nx.DiGraph(G_multi)
del G_multi
gc.collect()

print(f"   Graph Ready. Nodes: {len(G.nodes):,}")

# --- 2. Generate Data ---
print(f"2. Generating {TOTAL_TRIPS} mock trips...")
np.random.seed(42)
# Bounds: Squamish to Hope to Border
north, south = 50.75, 49.05
east, west = -121.35, -123.25

orig_x = np.random.uniform(east, west, TOTAL_TRIPS)
orig_y = np.random.uniform(south, north, TOTAL_TRIPS)
dest_x = np.random.uniform(east, west, TOTAL_TRIPS)
dest_y = np.random.uniform(south, north, TOTAL_TRIPS)

print("   Projecting inputs to Match Graph...")
# Input is Lat/Lon (4326), Graph is UTM (32610)
gdf_orig = gpd.GeoDataFrame(geometry=gpd.points_from_xy(orig_x, orig_y), crs="EPSG:4326").to_crs(target_crs)
gdf_dest = gpd.GeoDataFrame(geometry=gpd.points_from_xy(dest_x, dest_y), crs="EPSG:4326").to_crs(target_crs)

# --- 3. Pre-Snap ---
print("3. Pre-Snapping Coordinates...")
snap_start = time.time()
orig_nodes = ox.nearest_nodes(G, gdf_orig.geometry.x, gdf_orig.geometry.y)
dest_nodes = ox.nearest_nodes(G, gdf_dest.geometry.x, gdf_dest.geometry.y)
print(f"   Snapping complete in {time.time()-snap_start:.2f}s")

trips_df = pd.DataFrame({
    'trip_id': range(TOTAL_TRIPS),
    'orig_node': orig_nodes,
    'dest_node': dest_nodes
})

# --- 4. Worker Function ---
def calculate_chunk(indices):
    subset = trips_df.iloc[indices]

    # Route
    routes = ox.shortest_path(G, subset['orig_node'], subset['dest_node'], weight='travel_time')

    dist_list = []
    time_list = []
    valid_routes = []

    for route in routes:
        if route is None:
            dist_list.append(np.nan)
            time_list.append(np.nan)
            valid_routes.append(None)
        else:
            # Fast Summation Loop
            d = 0.0
            t = 0.0
            for u, v in zip(route[:-1], route[1:]):
                edge = G[u][v]
                d += edge.get('length', 0)
                t += edge.get('travel_time', 0)

            dist_list.append(d / 1000) # km
            time_list.append(t)        # min
            valid_routes.append(route)

    return indices, dist_list, time_list, valid_routes

# --- 5. Execution ---
print(f"4. Running Simulation on {NUM_CORES} Cores...")
print("-" * 100)

global_start = time.time()
all_distances = [np.nan] * TOTAL_TRIPS
all_times = [np.nan] * TOTAL_TRIPS
longest_route_data = {'dist': -1, 'route': None, 'id': -1}

indices = list(range(TOTAL_TRIPS))
chunks = [indices[i:i + CHUNK_SIZE] for i in range(0, len(indices), CHUNK_SIZE)]

with Pool(processes=NUM_CORES) as pool:
    completed = 0
    for idx_list, d_list, t_list, r_list in pool.imap_unordered(calculate_chunk, chunks):
        for i, idx in enumerate(idx_list):
            dist = d_list[i]
            all_distances[idx] = dist
            all_times[idx] = t_list[i]
            if dist is not np.nan and dist > longest_route_data['dist']:
                longest_route_data['dist'] = dist
                longest_route_data['route'] = r_list[i]
                longest_route_data['id'] = idx

        completed += len(idx_list)

        # Progress Bar
        elapsed = time.time() - global_start
        rate = completed / elapsed if elapsed > 0 else 0
        percent = completed / TOTAL_TRIPS
        remaining = TOTAL_TRIPS - completed
        eta = remaining / rate if rate > 0 else 0

        bar_len = 30
        filled = int(bar_len * percent)
        bar = '█' * filled + '-' * (bar_len - filled)

        sys.stdout.write(f"\r|{bar}| {percent:.1%} | {completed}/{TOTAL_TRIPS} | ETA: {eta:.0f}s | {int(rate)} routes/s")
        sys.stdout.flush()

print("\n" + "-" * 100)

# --- 6. Report ---
trips_df['distance_km'] = all_distances
trips_df['travel_time_min'] = all_times
successful = trips_df['distance_km'].notna().sum()

print(f"COMPLETE. Total Time: {time.time()-global_start:.1f}s")
print(f"Success Rate: {successful}/{TOTAL_TRIPS} ({(successful/TOTAL_TRIPS)*100:.1f}%)")

print("\n--- STATISTICS ---")
print(trips_df[['distance_km', 'travel_time_min']].describe().round(2))

def plot_route_safe(G_digraph, route, title="Route"):
    print(f"\nGenerating plot for: {title}...")
    G_plot = nx.MultiDiGraph(G_digraph)
    fig, ax = ox.plot_graph_route(
        G_plot, route, 
        route_linewidth=4, node_size=0, 
        bgcolor='black', edge_color='#333333', route_color='cyan'
    )
    plt.show()import osmnx as ox
import networkx as nx
import pandas as pd
import geopandas as gpd
import numpy as np
import time
import gc
import psutil
import os
import sys
import matplotlib.pyplot as plt
import contextily as ctx # Import for basemaps
from multiprocessing import Pool, cpu_count

# --- Configuration ---
CHUNK_SIZE = 100        # Frequent updates for smoother progress bar
TOTAL_TRIPS = 1000      # 1,000 trips
GRAPH_FILE = "BC_GOLDEN_REPAIRED.graphml" # Loading the repaired file
NUM_CORES = 8          

print(f"🏁 PRODUCTION START. RAM: {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MB")

# --- 1. Load Optimized Graph ---
print("1. Loading Golden Graph...")
# OSMnx loads as MultiDiGraph
G_multi = ox.load_graphml(GRAPH_FILE)
target_crs = G_multi.graph['crs']

# Flatten to DiGraph for High-Speed Routing
# This enables O(1) attribute lookup and prevents plotting errors
G = nx.DiGraph(G_multi)
del G_multi
gc.collect()

print(f"   Graph Ready. Nodes: {len(G.nodes):,}")

# Check Connectivity
print("   Checking graph connectivity...")
is_connected = nx.is_strongly_connected(G)
print(f"   Graph is strongly connected: {is_connected}")
if not is_connected:
    num_components = nx.number_strongly_connected_components(G)
    print(f"   ⚠️ WARNING: Graph has {num_components} disconnected components. Routing may fail.")

# --- 2. Generate Data ---
print(f"2. Generating {TOTAL_TRIPS} mock trips...")
np.random.seed(42)
# Bounds: Squamish to Hope to Border
north, south = 50.75, 49.05
east, west = -121.35, -123.25

orig_x = np.random.uniform(east, west, TOTAL_TRIPS)
orig_y = np.random.uniform(south, north, TOTAL_TRIPS)
dest_x = np.random.uniform(east, west, TOTAL_TRIPS)
dest_y = np.random.uniform(south, north, TOTAL_TRIPS)

print("   Projecting inputs to Match Graph...")
# Input is Lat/Lon (4326), Graph is UTM (32610)
gdf_orig = gpd.GeoDataFrame(geometry=gpd.points_from_xy(orig_x, orig_y), crs="EPSG:4326").to_crs(target_crs)
gdf_dest = gpd.GeoDataFrame(geometry=gpd.points_from_xy(dest_x, dest_y), crs="EPSG:4326").to_crs(target_crs)

# --- 3. Pre-Snap ---
print("3. Pre-Snapping Coordinates...")
snap_start = time.time()
orig_nodes = ox.nearest_nodes(G, gdf_orig.geometry.x, gdf_orig.geometry.y)
dest_nodes = ox.nearest_nodes(G, gdf_dest.geometry.x, gdf_dest.geometry.y)
print(f"   Snapping complete in {time.time()-snap_start:.2f}s")

trips_df = pd.DataFrame({
    'trip_id': range(TOTAL_TRIPS),
    'orig_node': orig_nodes,
    'dest_node': dest_nodes
})

# --- 4. Worker Function ---
def calculate_chunk(indices):
    subset = trips_df.iloc[indices]

    # Route
    try:
        routes = ox.shortest_path(G, subset['orig_node'], subset['dest_node'], weight='travel_time')
    except nx.NetworkXNoPath:
        routes = [None] * len(subset)

    dist_list = []
    time_list = []
    valid_routes = []

    for route in routes:
        if route is None:
            dist_list.append(np.nan)
            time_list.append(np.nan)
            valid_routes.append(None)
        else:
            # Fast Summation Loop
            d = 0.0
            t = 0.0
            for u, v in zip(route[:-1], route[1:]):
                edge = G[u][v]
                d += edge.get('length', 0)
                t += edge.get('travel_time', 0)

            dist_list.append(d / 1000) # km
            time_list.append(t)        # min
            valid_routes.append(route)

    return indices, dist_list, time_list, valid_routes

# --- 5. Execution ---
print(f"4. Running Simulation on {NUM_CORES} Cores...")
print("-" * 100)

global_start = time.time()
all_distances = [np.nan] * TOTAL_TRIPS
all_times = [np.nan] * TOTAL_TRIPS
longest_route_data = {'dist': -1, 'route': None, 'id': -1}

indices = list(range(TOTAL_TRIPS))
chunks = [indices[i:i + CHUNK_SIZE] for i in range(0, len(indices), CHUNK_SIZE)]

with Pool(processes=NUM_CORES) as pool:
    completed = 0
    for idx_list, d_list, t_list, r_list in pool.imap_unordered(calculate_chunk, chunks):
        for i, idx in enumerate(idx_list):
            dist = d_list[i]
            all_distances[idx] = dist
            all_times[idx] = t_list[i]
            if dist is not np.nan and dist > longest_route_data['dist']:
                longest_route_data['dist'] = dist
                longest_route_data['route'] = r_list[i]
                longest_route_data['id'] = idx

        completed += len(idx_list)

        # Progress Bar
        elapsed = time.time() - global_start
        rate = completed / elapsed if elapsed > 0 else 0
        percent = completed / TOTAL_TRIPS
        remaining = TOTAL_TRIPS - completed
        eta = remaining / rate if rate > 0 else 0

        bar_len = 30
        filled = int(bar_len * percent)
        bar = '█' * filled + '-' * (bar_len - filled)

        sys.stdout.write(f"\r|{bar}| {percent:.1%} | {completed}/{TOTAL_TRIPS} | ETA: {eta:.0f}s | {int(rate)} routes/s")
        sys.stdout.flush()

print("\n" + "-" * 100)

# --- 6. Report ---
trips_df['distance_km'] = all_distances
trips_df['travel_time_min'] = all_times
successful = trips_df['distance_km'].notna().sum()

print(f"COMPLETE. Total Time: {time.time()-global_start:.1f}s")
print(f"Success Rate: {successful}/{TOTAL_TRIPS} ({(successful/TOTAL_TRIPS)*100:.1f}%)")

print("\n--- STATISTICS ---")
print(trips_df[['distance_km', 'travel_time_min']].describe().round(2))

def plot_route_with_basemap(G_digraph, route, title="Route"):
    print(f"\nGenerating plot for: {title}...")

    # 1. Convert route to GeoDataFrame
    route_nodes = [G_digraph.nodes[n] for n in route]
    gdf_route = gpd.GeoDataFrame(route_nodes, geometry=gpd.points_from_xy([n['x'] for n in route_nodes], [n['y'] for n in route_nodes]), crs=G_digraph.graph['crs'])
    # Create a LineString from the points
    from shapely.geometry import LineString
    line = LineString(gdf_route.geometry.tolist())
    gdf_line = gpd.GeoDataFrame(geometry=[line], crs=G_digraph.graph['crs'])

    # 2. Reproject to Web Mercator for contextily
    gdf_line_wm = gdf_line.to_crs(epsg=3857)

    # 3. Plot
    fig, ax = plt.subplots(figsize=(10, 10))
    gdf_line_wm.plot(ax=ax, color='cyan', linewidth=4, alpha=0.8, zorder=2)

    # 4. Add Basemap
    try:
        ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
    except Exception as e:
        print(f"Could not fetch basemap: {e}")

    ax.set_title(title)
    ax.set_axis_off()
    plt.show()

if longest_route_data['route']:
    long_id = longest_route_data['id']
    dist = longest_route_data['dist']
    print(f"\n🏆 Longest Route (ID {long_id}): {dist:.1f} km")
    # Use the new basemap plotting function
    plot_route_with_basemap(G, longest_route_data['route'], title=f"Trip {long_id}")
else:
    print("\nNo routes found to plot.")

if longest_route_data['route']:
    long_id = longest_route_data['id']
    dist = longest_route_data['dist']
    print(f"\n🏆 Longest Route (ID {long_id}): {dist:.1f} km")
    plot_route_safe(G, longest_route_data['route'], title=f"Trip {long_id}")
else:
    print("\nNo routes found to plot.")


# Checking geo base data 

# In[6]:


import geopandas as gpd
import fiona
import pandas as pd

# Configure pandas to show all columns
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

FILENAME = "NRN_BC_14_0_GPKG_en.gpkg"

print(f"🔍 INSPECTING: {FILENAME}")
print("-" * 50)

# --- 1. LIST LAYERS (The Table of Contents) ---
print("1. CHECKING LAYERS...")
try:
    layers = fiona.listlayers(FILENAME)
    print(f"   Found {len(layers)} layers:")
    for i, layer in enumerate(layers):
        print(f"   [{i}] {layer}")
except Exception as e:
    print(f"❌ Error reading layers: {e}")
    exit()

# --- 2. DEEP DIVE INTO ROAD SEGMENTS ---
# We assume the layer with 'ROADSEG' in the name is the one we want
road_layer = next((l for l in layers if 'ROADSEG' in l), None)

if road_layer:
    print("\n" + "-" * 50)
    print(f"2. ANALYZING TARGET LAYER: '{road_layer}'")

    # Use fiona to get metadata without loading the whole file (Fast)
    with fiona.open(FILENAME, layer=road_layer) as src:
        print(f"   Feature Count: {len(src):,}")
        print(f"   CRS (Projection): {src.crs}")
        print(f"   Geometry Type: {src.schema['geometry']}")
        print(f"   Bounds (West, South, East, North): {src.bounds}")

        # Check if bounds look like Lat/Lon (-180 to 180) or Meters (huge numbers)
        if -180 <= src.bounds[0] <= 180:
            print("   👉 NOTE: Data appears to be in Degrees (Lat/Lon).")
        else:
            print("   👉 NOTE: Data appears to be Projected (Meters).")

    # --- 3. DATA FORMAT & SAMPLE ---
    print("\n" + "-" * 50)
    print("3. DATA TYPES & CONTENT SAMPLE")
    print("   Loading first 100 rows for inspection...")

    # Load small sample with GeoPandas
    gdf_sample = gpd.read_file(FILENAME, layer=road_layer, rows=100)

    # Show Column Data Types
    print("\n   [COLUMN DATA TYPES]")
    print(gdf_sample.dtypes)

    # Specific check for SPEED and ROADCLASS
    print("\n   [CRITICAL COLUMNS INSPECTION]")
    if 'SPEED' in gdf_sample.columns:
        unique_speeds = gdf_sample['SPEED'].unique()
        print(f"   Unique Speeds found in sample: {unique_speeds}")
        print(f"   Speed Column Type: {gdf_sample['SPEED'].dtype}")
    else:
        print("   ⚠️ WARNING: 'SPEED' column not found!")

    if 'ROADCLASS' in gdf_sample.columns:
        print(f"   Road Classes in sample: {gdf_sample['ROADCLASS'].unique()}")

    if 'PAVSURF' in gdf_sample.columns:
        print(f"   Paving Surfaces in sample: {gdf_sample['PAVSURF'].unique()}")

    # --- 4. GEOMETRY CHECK ---
    print("\n" + "-" * 50)
    print("4. RAW GEOMETRY CHECK")
    # Check for empty or invalid geometries in sample
    invalid_count = (~gdf_sample.geometry.is_valid).sum()
    empty_count = gdf_sample.geometry.is_empty.sum()

    print(f"   Invalid Geometries in sample: {invalid_count}")
    print(f"   Empty Geometries in sample: {empty_count}")
    print(f"   Sample WKT (First feature): {str(gdf_sample.geometry.iloc[0])[:100]}...")

else:
    print("❌ Could not find a 'ROADSEG' layer to inspect.")


# 🏎️ The "Production" Script (Adjusted for Detail)

# In[4]:


import osmnx as ox
import networkx as nx
import pandas as pd
import geopandas as gpd
import numpy as np
import time
import gc
import psutil
import os
import sys
import matplotlib.pyplot as plt
from multiprocessing import Pool, cpu_count

# --- Configuration ---
CHUNK_SIZE = 100        # Frequent updates
TOTAL_TRIPS = 1000      # 1,000 trips
GRAPH_FILE = "BC_GOLDEN_REPAIRED.graphml" # UPDATED to Repaired File
NUM_CORES = 8          

print(f"🏁 PRODUCTION START. RAM: {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MB")

# --- 1. Load Optimized Graph ---
print("1. Loading Golden Graph...")
# OSMnx loads as MultiDiGraph
G_multi = ox.load_graphml(GRAPH_FILE)
target_crs = G_multi.graph['crs']

# Flatten to DiGraph for High-Speed Routing
# This enables O(1) attribute lookup and prevents plotting errors
G = nx.DiGraph(G_multi)
del G_multi
gc.collect()

print(f"   Graph Ready. Nodes: {len(G.nodes):,}")

# --- 2. Generate Data ---
print(f"2. Generating {TOTAL_TRIPS} mock trips...")
np.random.seed(42)
# Bounds: Squamish to Hope to Border
north, south = 50.75, 49.05
east, west = -121.35, -123.25

orig_x = np.random.uniform(east, west, TOTAL_TRIPS)
orig_y = np.random.uniform(south, north, TOTAL_TRIPS)
dest_x = np.random.uniform(east, west, TOTAL_TRIPS)
dest_y = np.random.uniform(south, north, TOTAL_TRIPS)

print("   Projecting inputs to Match Graph...")
# Input is Lat/Lon (4326), Graph is UTM (32610)
gdf_orig = gpd.GeoDataFrame(geometry=gpd.points_from_xy(orig_x, orig_y), crs="EPSG:4326").to_crs(target_crs)
gdf_dest = gpd.GeoDataFrame(geometry=gpd.points_from_xy(dest_x, dest_y), crs="EPSG:4326").to_crs(target_crs)

# --- 3. Pre-Snap ---
print("3. Pre-Snapping Coordinates...")
snap_start = time.time()
orig_nodes = ox.nearest_nodes(G, gdf_orig.geometry.x, gdf_orig.geometry.y)
dest_nodes = ox.nearest_nodes(G, gdf_dest.geometry.x, gdf_dest.geometry.y)
print(f"   Snapping complete in {time.time()-snap_start:.2f}s")

trips_df = pd.DataFrame({
    'trip_id': range(TOTAL_TRIPS),
    'orig_node': orig_nodes,
    'dest_node': dest_nodes
})

# --- 4. Worker Function ---
def calculate_chunk(indices):
    subset = trips_df.iloc[indices]

    # Route
    routes = ox.shortest_path(G, subset['orig_node'], subset['dest_node'], weight='travel_time')

    dist_list = []
    time_list = []
    valid_routes = []

    for route in routes:
        if route is None:
            dist_list.append(np.nan)
            time_list.append(np.nan)
            valid_routes.append(None)
        else:
            # Fast Summation Loop
            d = 0.0
            t = 0.0
            for u, v in zip(route[:-1], route[1:]):
                edge = G[u][v]
                d += edge.get('length', 0)
                t += edge.get('travel_time', 0)

            dist_list.append(d / 1000) # km
            time_list.append(t)        # min
            valid_routes.append(route)

    return indices, dist_list, time_list, valid_routes

# --- 5. Execution ---
print(f"4. Running Simulation on {NUM_CORES} Cores...")
print("-" * 100)

global_start = time.time()
all_distances = [np.nan] * TOTAL_TRIPS
all_times = [np.nan] * TOTAL_TRIPS
longest_route_data = {'dist': -1, 'route': None, 'id': -1}

indices = list(range(TOTAL_TRIPS))
chunks = [indices[i:i + CHUNK_SIZE] for i in range(0, len(indices), CHUNK_SIZE)]

with Pool(processes=NUM_CORES) as pool:
    completed = 0
    for idx_list, d_list, t_list, r_list in pool.imap_unordered(calculate_chunk, chunks):
        for i, idx in enumerate(idx_list):
            dist = d_list[i]
            all_distances[idx] = dist
            all_times[idx] = t_list[i]
            if dist is not np.nan and dist > longest_route_data['dist']:
                longest_route_data['dist'] = dist
                longest_route_data['route'] = r_list[i]
                longest_route_data['id'] = idx

        completed += len(idx_list)

        # Progress Bar
        elapsed = time.time() - global_start
        rate = completed / elapsed if elapsed > 0 else 0
        percent = completed / TOTAL_TRIPS
        remaining = TOTAL_TRIPS - completed
        eta = remaining / rate if rate > 0 else 0

        bar_len = 30
        filled = int(bar_len * percent)
        bar = '█' * filled + '-' * (bar_len - filled)

        sys.stdout.write(f"\r|{bar}| {percent:.1%} | {completed}/{TOTAL_TRIPS} | ETA: {eta:.0f}s | {int(rate)} routes/s")
        sys.stdout.flush()

print("\n" + "-" * 100)

# --- 6. Report ---
trips_df['distance_km'] = all_distances
trips_df['travel_time_min'] = all_times
successful = trips_df['distance_km'].notna().sum()

print(f"COMPLETE. Total Time: {time.time()-global_start:.1f}s")
print(f"Success Rate: {successful}/{TOTAL_TRIPS} ({(successful/TOTAL_TRIPS)*100:.1f}%)")

print("\n--- STATISTICS ---")
print(trips_df[['distance_km', 'travel_time_min']].describe().round(2))

# --- UPDATED PLOT FUNCTION ---
def plot_route_safe(G_digraph, route, title="Route"):
    print(f"\nGenerating Zoomed Plot for: {title}...")

    # 1. Calculate Bounding Box of the Route (in Meters)
    x_vals = [G_digraph.nodes[n]['x'] for n in route]
    y_vals = [G_digraph.nodes[n]['y'] for n in route]

    min_x, max_x = min(x_vals), max(x_vals)
    min_y, max_y = min(y_vals), max(y_vals)

    # Add Margin (10% padding or at least 2km)
    margin_x = max((max_x - min_x) * 0.1, 2000)
    margin_y = max((max_y - min_y) * 0.1, 2000)

    west, east = min_x - margin_x, max_x + margin_x
    south, north = min_y - margin_y, max_y + margin_y

    # 2. Extract Subgraph (Efficient Filtering)
    print("   Extracting local street network...")
    nodes_in_bbox = [
        n for n, d in G_digraph.nodes(data=True) 
        if west < d['x'] < east and south < d['y'] < north
    ]

    # Ensure route nodes are included
    nodes_to_keep = set(nodes_in_bbox) | set(route)
    G_sub = G_digraph.subgraph(nodes_to_keep)

    # 3. Cast to MultiDiGraph for OSMnx plotting
    G_plot = nx.MultiDiGraph(G_sub)

    # 4. Plot
    fig, ax = ox.plot_graph_route(
        G_plot, route, 
        route_linewidth=4, 
        node_size=0, 
        bgcolor='white',          # White background
        edge_color='#999999',     # Light Grey streets
        edge_linewidth=0.5,       # Thin street lines
        route_color='red',        # Red Route
        route_alpha=0.9,
        show=False, close=False
    )
    ax.set_title(title, fontsize=12, color='black')
    plt.show()

if longest_route_data['route']:
    long_id = longest_route_data['id']
    dist = longest_route_data['dist']
    print(f"\n🏆 Longest Route (ID {long_id}): {dist:.1f} km")
    plot_route_safe(G, longest_route_data['route'], title=f"Trip {long_id} ({dist:.0f}km)")
else:
    print("\nNo routes found to plot.")


# Fixing bad map and viz with folium:

# In[6]:


get_ipython().run_line_magic('pip', 'install folium -q')


# In[1]:


import osmnx as ox
import networkx as nx
import pandas as pd
import geopandas as gpd
import numpy as np
import time
import gc
import psutil
import os
import sys
import folium  # <--- Added for interactive maps
from multiprocessing import Pool, cpu_count

# --- Configuration ---
CHUNK_SIZE = 100        # Frequent updates
TOTAL_TRIPS = 1000      # 1,000 trips
GRAPH_FILE = "BC_GOLDEN_REPAIRED.graphml" 
NUM_CORES = 8          

print(f"🏁 PRODUCTION START. RAM: {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MB")

# --- 1. Load Optimized Graph ---
print("1. Loading Golden Graph...")
G_multi = ox.load_graphml(GRAPH_FILE)
target_crs = G_multi.graph['crs']

# Flatten to DiGraph
G = nx.DiGraph(G_multi)
del G_multi
gc.collect()

print(f"   Graph Ready. Nodes: {len(G.nodes):,}")

# --- 2. Generate Data ---
print(f"2. Generating {TOTAL_TRIPS} mock trips...")
np.random.seed(42)
# Bounds: Squamish to Hope to Border
north, south = 50.75, 49.05
east, west = -121.35, -123.25

orig_x = np.random.uniform(east, west, TOTAL_TRIPS)
orig_y = np.random.uniform(south, north, TOTAL_TRIPS)
dest_x = np.random.uniform(east, west, TOTAL_TRIPS)
dest_y = np.random.uniform(south, north, TOTAL_TRIPS)

print("   Projecting inputs to Match Graph...")
# Input is Lat/Lon (4326), Graph is UTM (32610)
gdf_orig = gpd.GeoDataFrame(geometry=gpd.points_from_xy(orig_x, orig_y), crs="EPSG:4326").to_crs(target_crs)
gdf_dest = gpd.GeoDataFrame(geometry=gpd.points_from_xy(dest_x, dest_y), crs="EPSG:4326").to_crs(target_crs)

# --- 3. Pre-Snap ---
print("3. Pre-Snapping Coordinates...")
snap_start = time.time()
orig_nodes = ox.nearest_nodes(G, gdf_orig.geometry.x, gdf_orig.geometry.y)
dest_nodes = ox.nearest_nodes(G, gdf_dest.geometry.x, gdf_dest.geometry.y)
print(f"   Snapping complete in {time.time()-snap_start:.2f}s")

trips_df = pd.DataFrame({
    'trip_id': range(TOTAL_TRIPS),
    'orig_node': orig_nodes,
    'dest_node': dest_nodes
})

# --- 4. Worker Function ---
def calculate_chunk(indices):
    subset = trips_df.iloc[indices]
    routes = ox.shortest_path(G, subset['orig_node'], subset['dest_node'], weight='travel_time')

    dist_list = []
    time_list = []
    valid_routes = []

    for route in routes:
        if route is None:
            dist_list.append(np.nan)
            time_list.append(np.nan)
            valid_routes.append(None)
        else:
            d = 0.0
            t = 0.0
            for u, v in zip(route[:-1], route[1:]):
                edge = G[u][v]
                d += edge.get('length', 0)
                t += edge.get('travel_time', 0)
            dist_list.append(d / 1000)
            time_list.append(t)
            valid_routes.append(route)

    return indices, dist_list, time_list, valid_routes

# --- 5. Execution ---
print(f"4. Running Simulation on {NUM_CORES} Cores...")
print("-" * 100)

global_start = time.time()
all_distances = [np.nan] * TOTAL_TRIPS
all_times = [np.nan] * TOTAL_TRIPS
longest_route_data = {'dist': -1, 'route': None, 'id': -1}

indices = list(range(TOTAL_TRIPS))
chunks = [indices[i:i + CHUNK_SIZE] for i in range(0, len(indices), CHUNK_SIZE)]

with Pool(processes=NUM_CORES) as pool:
    completed = 0
    for idx_list, d_list, t_list, r_list in pool.imap_unordered(calculate_chunk, chunks):
        for i, idx in enumerate(idx_list):
            dist = d_list[i]
            all_distances[idx] = dist
            all_times[idx] = t_list[i]
            if dist is not np.nan and dist > longest_route_data['dist']:
                longest_route_data['dist'] = dist
                longest_route_data['route'] = r_list[i]
                longest_route_data['id'] = idx

        completed += len(idx_list)

        elapsed = time.time() - global_start
        rate = completed / elapsed if elapsed > 0 else 0
        percent = completed / TOTAL_TRIPS
        remaining = TOTAL_TRIPS - completed
        eta = remaining / rate if rate > 0 else 0
        bar = '█' * int(30 * percent) + '-' * (30 - int(30 * percent))
        sys.stdout.write(f"\r|{bar}| {percent:.1%} | {completed}/{TOTAL_TRIPS} | ETA: {eta:.0f}s | {int(rate)} routes/s")
        sys.stdout.flush()

print("\n" + "-" * 100)

# --- 6. Report ---
trips_df['distance_km'] = all_distances
trips_df['travel_time_min'] = all_times
successful = trips_df['distance_km'].notna().sum()

print(f"COMPLETE. Total Time: {time.time()-global_start:.1f}s")
print(f"Success Rate: {successful}/{TOTAL_TRIPS} ({(successful/TOTAL_TRIPS)*100:.1f}%)")

print("\n--- STATISTICS ---")
print(trips_df[['distance_km', 'travel_time_min']].describe().round(2))

# --- NEW: INTERACTIVE MAP FUNCTION (FOLIUM) ---
def plot_route_folium(G_digraph, route, title="Route"):
    print(f"\nGeneratng Interactive Map for: {title}...")

    # 1. Extract Node Coordinates from Graph
    # The graph is in UTM (Meters), we need Lat/Lon for Folium
    print("   Extracting and Reprojecting Route Geometry...")
    route_nodes = [G_digraph.nodes[n] for n in route]

    # Create GeoDataFrame to handle reprojection easily
    gdf_nodes = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy(
            [n['x'] for n in route_nodes], 
            [n['y'] for n in route_nodes]
        ), 
        crs=G_digraph.graph['crs']
    )

    # Reproject to EPSG:4326 (Lat/Lon)
    gdf_nodes = gdf_nodes.to_crs(epsg=4326)

    # Extract (Lat, Lon) tuples for Folium
    route_coords = [(p.y, p.x) for p in gdf_nodes.geometry]

    # 2. Create Map centered on the route
    mid_point = route_coords[len(route_coords)//2]
    m = folium.Map(location=mid_point, zoom_start=10, tiles='OpenStreetMap')

    # 3. Add Route Line
    folium.PolyLine(
        route_coords, 
        color="red", 
        weight=5, 
        opacity=0.8,
        tooltip=title
    ).add_to(m)

    # 4. Add Start/End Markers
    folium.Marker(route_coords[0], popup="Start", icon=folium.Icon(color="green", icon="play")).add_to(m)
    folium.Marker(route_coords[-1], popup="End", icon=folium.Icon(color="red", icon="stop")).add_to(m)

    # 5. Save
    outfile = "longest_route_map.html"
    m.save(outfile)
    print(f"✅ Map saved to '{outfile}'. Open this file in your browser to explore!")

if longest_route_data['route']:
    long_id = longest_route_data['id']
    dist = longest_route_data['dist']
    print(f"\n🏆 Longest Route (ID {long_id}): {dist:.1f} km")
    plot_route_folium(G, longest_route_data['route'], title=f"Trip {long_id} ({dist:.0f}km)")
else:
    print("\nNo routes found to plot.")


# Reproduce and Inspect with ipywidgets: 

# In[2]:


get_ipython().run_line_magic('pip', 'install ipywidgets ipyleaflet IPython -q')


# In[2]:


import osmnx as ox
import networkx as nx
import pandas as pd
import geopandas as gpd
import numpy as np
import time
import gc
import psutil
import os
import sys
# --- WIDGET IMPORTS ---
import ipywidgets as widgets
from ipyleaflet import Map, Polyline, Marker, AwesomeIcon, basemaps
from IPython.display import display
from multiprocessing import Pool, cpu_count

# --- Configuration ---
CHUNK_SIZE = 100        
TOTAL_TRIPS = 1000      
GRAPH_FILE = "BC_GOLDEN_REPAIRED.graphml" 
NUM_CORES = 8          

print(f"🏁 PRODUCTION START. RAM: {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MB")

# --- 1. Load Optimized Graph ---
print("1. Loading Golden Graph...")
G_multi = ox.load_graphml(GRAPH_FILE)
target_crs = G_multi.graph['crs']

# Flatten to DiGraph
G = nx.DiGraph(G_multi)
del G_multi
gc.collect()

print(f"   Graph Ready. Nodes: {len(G.nodes):,}")

# --- 2. Generate Data (URBAN SKEW) ---
print(f"2. Generating {TOTAL_TRIPS} mock trips (Urban Focused)...")
np.random.seed(42)

# UPDATED BOUNDS: Metro Vancouver & Fraser Valley
# Excludes the northern wilderness (Squamish/Lillooet)
north, south = 49.40, 49.00
east, west = -121.75, -123.30

orig_x = np.random.uniform(east, west, TOTAL_TRIPS)
orig_y = np.random.uniform(south, north, TOTAL_TRIPS)
dest_x = np.random.uniform(east, west, TOTAL_TRIPS)
dest_y = np.random.uniform(south, north, TOTAL_TRIPS)

print("   Projecting inputs to Match Graph...")
gdf_orig = gpd.GeoDataFrame(geometry=gpd.points_from_xy(orig_x, orig_y), crs="EPSG:4326").to_crs(target_crs)
gdf_dest = gpd.GeoDataFrame(geometry=gpd.points_from_xy(dest_x, dest_y), crs="EPSG:4326").to_crs(target_crs)

# --- 3. Pre-Snap ---
print("3. Pre-Snapping Coordinates...")
snap_start = time.time()
orig_nodes = ox.nearest_nodes(G, gdf_orig.geometry.x, gdf_orig.geometry.y)
dest_nodes = ox.nearest_nodes(G, gdf_dest.geometry.x, gdf_dest.geometry.y)
print(f"   Snapping complete in {time.time()-snap_start:.2f}s")

trips_df = pd.DataFrame({
    'trip_id': range(TOTAL_TRIPS),
    'orig_node': orig_nodes,
    'dest_node': dest_nodes
})

# --- 4. Worker Function ---
def calculate_chunk(indices):
    subset = trips_df.iloc[indices]
    routes = ox.shortest_path(G, subset['orig_node'], subset['dest_node'], weight='travel_time')

    dist_list = []
    time_list = []
    valid_routes = []

    for route in routes:
        if route is None:
            dist_list.append(np.nan)
            time_list.append(np.nan)
            valid_routes.append(None)
        else:
            d = 0.0
            t = 0.0
            for u, v in zip(route[:-1], route[1:]):
                edge = G[u][v]
                d += edge.get('length', 0)
                t += edge.get('travel_time', 0)
            dist_list.append(d / 1000)
            time_list.append(t)
            valid_routes.append(route)

    return indices, dist_list, time_list, valid_routes

# --- 5. Execution ---
print(f"4. Running Simulation on {NUM_CORES} Cores...")
print("-" * 100)

global_start = time.time()
all_distances = [np.nan] * TOTAL_TRIPS
all_times = [np.nan] * TOTAL_TRIPS
longest_route_data = {'dist': -1, 'route': None, 'id': -1}

indices = list(range(TOTAL_TRIPS))
chunks = [indices[i:i + CHUNK_SIZE] for i in range(0, len(indices), CHUNK_SIZE)]

with Pool(processes=NUM_CORES) as pool:
    completed = 0
    for idx_list, d_list, t_list, r_list in pool.imap_unordered(calculate_chunk, chunks):
        for i, idx in enumerate(idx_list):
            dist = d_list[i]
            all_distances[idx] = dist
            all_times[idx] = t_list[i]
            if dist is not np.nan and dist > longest_route_data['dist']:
                longest_route_data['dist'] = dist
                longest_route_data['route'] = r_list[i]
                longest_route_data['id'] = idx

        completed += len(idx_list)

        elapsed = time.time() - global_start
        rate = completed / elapsed if elapsed > 0 else 0
        percent = completed / TOTAL_TRIPS
        remaining = TOTAL_TRIPS - completed
        eta = remaining / rate if rate > 0 else 0

        bar_len = 30
        filled = int(bar_len * percent)
        bar = '█' * filled + '-' * (bar_len - filled)

        sys.stdout.write(f"\r|{bar}| {percent:.1%} | {completed}/{TOTAL_TRIPS} | ETA: {eta:.0f}s | {int(rate)} routes/s")
        sys.stdout.flush()

print("\n" + "-" * 100)

# --- 6. Report ---
trips_df['distance_km'] = all_distances
trips_df['travel_time_min'] = all_times
successful = trips_df['distance_km'].notna().sum()

print(f"COMPLETE. Total Time: {time.time()-global_start:.1f}s")
print(f"Success Rate: {successful}/{TOTAL_TRIPS} ({(successful/TOTAL_TRIPS)*100:.1f}%)")

print("\n--- STATISTICS ---")
print(trips_df[['distance_km', 'travel_time_min']].describe().round(2))

# --- NEW: IPYLEAFLET WIDGET FUNCTION ---
def plot_route_widget(G_digraph, route, title="Route"):
    print(f"\nGenerating ipywidget Map for: {title}...")

    # 1. Extract & Reproject
    route_nodes = [G_digraph.nodes[n] for n in route]

    gdf_nodes = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy(
            [n['x'] for n in route_nodes], 
            [n['y'] for n in route_nodes]
        ), 
        crs=G_digraph.graph['crs']
    )

    # Reproject to Lat/Lon for Leaflet
    gdf_nodes = gdf_nodes.to_crs(epsg=4326)

    # Extract coords (Lat, Lon format for ipyleaflet)
    path_coords = [(p.y, p.x) for p in gdf_nodes.geometry]
    center = path_coords[len(path_coords)//2]

    # 2. Create Widget Map
    m = Map(
        basemap=basemaps.OpenStreetMap.Mapnik,
        center=center,
        zoom=10,
        layout=widgets.Layout(width='100%', height='600px')
    )

    # 3. Add Polyline
    line = Polyline(
        locations=path_coords,
        color="blue",
        fill=False,
        weight=5
    )
    m.add_layer(line)

    # 4. Add Markers
    start_icon = AwesomeIcon(name='play', marker_color='green', icon_color='white')
    end_icon = AwesomeIcon(name='stop', marker_color='red', icon_color='white')

    marker_start = Marker(location=path_coords[0], icon=start_icon, title="Start")
    marker_end = Marker(location=path_coords[-1], icon=end_icon, title="End")

    m.add_layer(marker_start)
    m.add_layer(marker_end)

    # Display the widget
    display(m)

if longest_route_data['route']:
    long_id = longest_route_data['id']
    dist = longest_route_data['dist']
    print(f"\n🏆 Longest Route (ID {long_id}): {dist:.1f} km")
    plot_route_widget(G, longest_route_data['route'], title=f"Trip {long_id} ({dist:.0f}km)")
else:
    print("\nNo routes found to plot.")


# Viz for 5 average trips:

# In[3]:


import ipywidgets as widgets
from ipyleaflet import Map, Polyline, Marker, AwesomeIcon, basemaps, LegendControl
from IPython.display import display
import geopandas as gpd
import osmnx as ox

# --- 1. Select 5 "Average" Trips ---
print("--- VISUALIZATION: 5 AVERAGE TRIPS ---")

# Filter for successful trips only
valid_trips = trips_df[trips_df['distance_km'].notna()].copy()

# Calculate Median
median_dist = valid_trips['distance_km'].median()
print(f"Median Trip Distance: {median_dist:.1f} km")

# Find the 5 trips closest to the median
valid_trips['diff_from_median'] = (valid_trips['distance_km'] - median_dist).abs()
average_trips = valid_trips.sort_values('diff_from_median').head(5)

print(f"Selected {len(average_trips)} representative trips for display.")

# --- 2. Re-Route & Prepare Geometry ---
colors = ['blue', 'green', 'purple', 'orange', 'red']
routes_data = []

print("Re-calculating paths for visualization...")
for i, (idx, row) in enumerate(average_trips.iterrows()):
    # Re-run single route calculation (Instant)
    route = ox.shortest_path(G, int(row['orig_node']), int(row['dest_node']), weight='travel_time')

    if route:
        # Extract nodes for the route
        route_nodes = [G.nodes[n] for n in route]

        # Create GeoDataFrame to handle projection easily
        gdf_route = gpd.GeoDataFrame(
            geometry=gpd.points_from_xy(
                [n['x'] for n in route_nodes], 
                [n['y'] for n in route_nodes]
            ), 
            crs=G.graph['crs'] # Use the graph's UTM projection
        )

        # Reproject to Lat/Lon (EPSG:4326) for Leaflet
        gdf_route = gdf_route.to_crs(epsg=4326)

        # Extract list of (Lat, Lon) tuples
        path_coords = [(p.y, p.x) for p in gdf_route.geometry]

        routes_data.append({
            'coords': path_coords,
            'color': colors[i % len(colors)],
            'title': f"Trip {row['trip_id']} ({row['distance_km']:.1f}km)"
        })

# --- 3. Render Interactive Map ---
if routes_data:
    print("Generating Interactive Map...")

    # Center map on the first route
    center = routes_data[0]['coords'][len(routes_data[0]['coords'])//2]

    m = Map(
        basemap=basemaps.OpenStreetMap.Mapnik,
        center=center,
        zoom=9,
        layout=widgets.Layout(width='100%', height='700px')
    )

    legend_content = {}

    for item in routes_data:
        # Add Line
        line = Polyline(
            locations=item['coords'],
            color=item['color'],
            fill=False,
            weight=4,
            opacity=0.8
        )
        m.add_layer(line)

        # Add Legend Item
        legend_content[item['title']] = item['color']

        # Add Markers
        start_icon = AwesomeIcon(name='play', marker_color=item['color'], icon_color='white')
        end_icon = AwesomeIcon(name='stop', marker_color=item['color'], icon_color='white')

        m.add_layer(Marker(location=item['coords'][0], icon=start_icon, title=f"Start: {item['title']}"))
        m.add_layer(Marker(location=item['coords'][-1], icon=end_icon, title=f"End: {item['title']}"))

    # Add Legend
    legend = LegendControl(legend_content, name="Average Trips", position="topright")
    m.add_control(legend)

    display(m)
else:
    print("No valid routes found to plot.")


# In[4]:


import ipywidgets as widgets
from ipyleaflet import Map, Polyline, Marker, AwesomeIcon, basemaps, LegendControl
from IPython.display import display
import geopandas as gpd
import osmnx as ox

# --- 1. Select 10 "Q1" (Short/Urban) Trips ---
print("--- VISUALIZATION: 10 LOWER QUARTILE (URBAN) TRIPS ---")

# Filter for successful trips only
valid_trips = trips_df[trips_df['distance_km'].notna()].copy()

# Calculate 25th Percentile (Q1)
q1_dist = valid_trips['distance_km'].quantile(0.25)
print(f"25th Percentile Distance: {q1_dist:.1f} km")

# Find the 10 trips closest to Q1
valid_trips['diff_from_q1'] = (valid_trips['distance_km'] - q1_dist).abs()
selected_trips = valid_trips.sort_values('diff_from_q1').head(10)

print(f"Selected {len(selected_trips)} representative trips for display.")

# --- 2. Re-Route & Prepare Geometry ---
# Expanded color palette for 10 routes
colors = [
    'blue', 'green', 'purple', 'orange', 'red', 
    'darkred', 'darkblue', 'darkgreen', 'cadetblue', 'pink'
]
routes_data = []

print("Re-calculating paths for visualization...")
for i, (idx, row) in enumerate(selected_trips.iterrows()):
    # Re-run single route calculation (Instant)
    route = ox.shortest_path(G, int(row['orig_node']), int(row['dest_node']), weight='travel_time')

    if route:
        # Extract nodes for the route
        route_nodes = [G.nodes[n] for n in route]

        # Create GeoDataFrame to handle projection easily
        gdf_route = gpd.GeoDataFrame(
            geometry=gpd.points_from_xy(
                [n['x'] for n in route_nodes], 
                [n['y'] for n in route_nodes]
            ), 
            crs=G.graph['crs'] # Use the graph's UTM projection
        )

        # Reproject to Lat/Lon (EPSG:4326) for Leaflet
        gdf_route = gdf_route.to_crs(epsg=4326)

        # Extract list of (Lat, Lon) tuples
        path_coords = [(p.y, p.x) for p in gdf_route.geometry]

        routes_data.append({
            'coords': path_coords,
            'color': colors[i % len(colors)],
            'title': f"Trip {row['trip_id']} ({row['distance_km']:.1f}km)"
        })

# --- 3. Render Interactive Map ---
if routes_data:
    print("Generating Interactive Map...")

    # Center map on the first route
    center = routes_data[0]['coords'][len(routes_data[0]['coords'])//2]

    m = Map(
        basemap=basemaps.OpenStreetMap.Mapnik,
        center=center,
        zoom=10, # Zoomed in slightly more for urban scale
        layout=widgets.Layout(width='100%', height='700px')
    )

    legend_content = {}

    for item in routes_data:
        # Add Line
        line = Polyline(
            locations=item['coords'],
            color=item['color'],
            fill=False,
            weight=4,
            opacity=0.8
        )
        m.add_layer(line)

        # Add Legend Item
        legend_content[item['title']] = item['color']

        # Add Markers
        start_icon = AwesomeIcon(name='play', marker_color=item['color'], icon_color='white')
        end_icon = AwesomeIcon(name='stop', marker_color=item['color'], icon_color='white')

        m.add_layer(Marker(location=item['coords'][0], icon=start_icon, title=f"Start: {item['title']}"))
        m.add_layer(Marker(location=item['coords'][-1], icon=end_icon, title=f"End: {item['title']}"))

    # Add Legend
    legend = LegendControl(legend_content, name="Short Urban Trips", position="topright")
    m.add_control(legend)

    display(m)
else:
    print("No valid routes found to plot.")


# Urban routes:

# In[5]:


import ipywidgets as widgets
from ipyleaflet import Map, Polyline, Marker, AwesomeIcon, basemaps, LegendControl
from IPython.display import display
import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry import Point

# --- 1. Select 10 Trips Closest to Vancouver (Urban) ---
print("--- VISUALIZATION: 10 TRIPS CLOSEST TO VANCOUVER ---")

# Define Target: Vancouver City Hall (Lat/Lon)
# We sort by proximity to this point to guarantee we find 'Urban' trips,
# regardless of how sparse the random generation was.
vancouver_center = Point(-123.1139, 49.2609)

# Create a GeoDataFrame of all trip Start Nodes to check locations
start_node_ids = trips_df['orig_node'].values
# Look up X/Y (Meters) from the Graph
node_coords = [
    (G.nodes[n]['x'], G.nodes[n]['y']) 
    for n in start_node_ids
]

# Create GDF in Graph's CRS (Meters)
gdf_starts = gpd.GeoDataFrame(
    {'trip_id': trips_df['trip_id'], 'distance_km': trips_df['distance_km']},
    geometry=gpd.points_from_xy([x for x, y in node_coords], [y for x, y in node_coords]),
    crs=G.graph['crs']
)

# Reproject to Lat/Lon
gdf_starts_latlon = gdf_starts.to_crs(epsg=4326)

# Calculate distance to Vancouver (in Degrees - sufficient for sorting)
gdf_starts_latlon['dist_to_center'] = gdf_starts_latlon.geometry.distance(vancouver_center)

# Filter: Only consider successful routes
valid_candidates = gdf_starts_latlon[gdf_starts_latlon['distance_km'].notna()]

# Sort by proximity and take top 10
top_10_urban = valid_candidates.sort_values('dist_to_center').head(10)
selected_trip_ids = top_10_urban['trip_id'].values

# Select from main DataFrame
selected_trips = trips_df[trips_df['trip_id'].isin(selected_trip_ids)]

print(f"Selected {len(selected_trips)} trips nearest to Vancouver core.")

# --- 2. Re-Route & Prepare Geometry ---
colors = [
    'blue', 'green', 'purple', 'orange', 'red', 
    'darkred', 'darkblue', 'darkgreen', 'cadetblue', 'pink'
]
routes_data = []

print("Re-calculating paths for visualization...")
for i, (idx, row) in enumerate(selected_trips.iterrows()):
    # Re-run single route calculation (Instant)
    route = ox.shortest_path(G, int(row['orig_node']), int(row['dest_node']), weight='travel_time')

    if route:
        # Extract nodes for the route
        route_nodes = [G.nodes[n] for n in route]

        # Create GeoDataFrame to handle projection easily
        gdf_route = gpd.GeoDataFrame(
            geometry=gpd.points_from_xy(
                [n['x'] for n in route_nodes], 
                [n['y'] for n in route_nodes]
            ), 
            crs=G.graph['crs'] # Use the graph's UTM projection
        )

        # Reproject to Lat/Lon (EPSG:4326) for Leaflet
        gdf_route = gdf_route.to_crs(epsg=4326)

        # Extract list of (Lat, Lon) tuples
        path_coords = [(p.y, p.x) for p in gdf_route.geometry]

        routes_data.append({
            'coords': path_coords,
            'color': colors[i % len(colors)],
            'title': f"Trip {int(row['trip_id'])} ({row['distance_km']:.1f}km)"
        })

# --- 3. Render Interactive Map ---
if routes_data:
    print("Generating Interactive Map...")

    # Center map on the first route
    center = routes_data[0]['coords'][len(routes_data[0]['coords'])//2]

    m = Map(
        basemap=basemaps.OpenStreetMap.Mapnik,
        center=center,
        zoom=11, 
        layout=widgets.Layout(width='100%', height='700px')
    )

    legend_content = {}

    for item in routes_data:
        # Add Line
        line = Polyline(
            locations=item['coords'],
            color=item['color'],
            fill=False,
            weight=4,
            opacity=0.8
        )
        m.add_layer(line)

        # Add Legend Item
        legend_content[item['title']] = item['color']

        # Add Markers
        start_icon = AwesomeIcon(name='play', marker_color=item['color'], icon_color='white')
        end_icon = AwesomeIcon(name='stop', marker_color=item['color'], icon_color='white')

        m.add_layer(Marker(location=item['coords'][0], icon=start_icon, title=f"Start: {item['title']}"))
        m.add_layer(Marker(location=item['coords'][-1], icon=end_icon, title=f"End: {item['title']}"))

    # Add Legend
    legend = LegendControl(legend_content, name="Urban Trips", position="topright")
    m.add_control(legend)

    display(m)
else:
    print("No valid routes found to plot.")


# DO ANEW:

# In[ ]:


import osmnx as ox
import networkx as nx
import geopandas as gpd
import pandas as pd
import numpy as np
import gc
import psutil
import os
from shapely.geometry import Point

print("🏁 FACTORY v11 (Highway Boost & Null-Island Nuke) STARTING...")

def get_ram():
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

print(f"   Initial RAM: {get_ram():.1f} MB")

# --- 1. Load Raw Data ---
print("1. Loading & Sanitizing NRN Data...")
gpkg_filename = "NRN_BC_14_0_GPKG_en.gpkg"
layer_name = "NRN_BC_14_0_ROADSEG"

try:
    # Load necessary columns including ROADJURIS
    keep_cols = ['geometry', 'SPEED', 'ROADCLASS', 'PAVSURF', 'PAVSTATUS', 'ROADJURIS']
    gdf_roads = gpd.read_file(gpkg_filename, layer=layer_name)

    # Prune immediately
    existing_cols = [c for c in keep_cols if c in gdf_roads.columns]
    gdf_roads = gdf_roads[existing_cols]

except Exception as e:
    print(f"❌ Error loading file: {e}")
    exit()

initial_len = len(gdf_roads)
print(f"   Loaded {initial_len} rows. RAM: {get_ram():.1f} MB")

# --- 2. QA & Sanitization ---
print("2. QA & Sanitization...")

# A. Remove Bad Geometries
gdf_roads = gdf_roads[gdf_roads.geometry.notna() & gdf_roads.geometry.is_valid]
# Filter out massive artifacts (> 2 degrees / ~220km)
gdf_roads = gdf_roads[gdf_roads.geometry.length < 2.0]
# Filter out tiny artifacts (< 1 meter)
gdf_roads = gdf_roads[gdf_roads.geometry.length > 0.00001] 

# B. Spatial Filter (BC Bounding Box - Strict)
gdf_roads = gdf_roads.cx[-140:-110, 48:62]

# C. ATTRIBUTE CLEANING
text_cols = ['ROADCLASS', 'PAVSURF', 'PAVSTATUS', 'ROADJURIS']
for col in text_cols:
    if col in gdf_roads.columns:
        gdf_roads[col] = gdf_roads[col].astype(str).str.title().replace({'None': 'Unknown', 'Nan': 'Unknown'})

# D. SPEED LOGIC (BOOSTED)
gdf_roads['SPEED'] = pd.to_numeric(gdf_roads['SPEED'], errors='coerce').fillna(-1)

# Aggressive Defaults for Highways
defaults = {
    'Freeway': 110,      # WAS 100, BOOSTED TO 110
    'Expressway': 100,   # WAS 90, BOOSTED TO 100
    'Arterial': 60, 
    'Collector': 50, 
    'Local': 40, 
    'Resource': 30, 
    'Ferry': 10,
    'Rapid Transit': 0
}

default_speeds = gdf_roads['ROADCLASS'].map(defaults).fillna(40)
# Use official speed if available (>0), otherwise use boosted default
gdf_roads['safe_speed'] = np.where(gdf_roads['SPEED'] <= 0, default_speeds, gdf_roads['SPEED'])

# Drop dirty column
gdf_roads = gdf_roads.drop(columns=['SPEED']) 
print(f"   Dropped {initial_len - len(gdf_roads)} bad rows.")
gc.collect()

# --- 3. Build Topology ---
print("3. Building Topology...")
gdf_roads['u_coord'] = gdf_roads.geometry.apply(lambda x: (round(x.coords[0][0], 6), round(x.coords[0][1], 6)))
gdf_roads['v_coord'] = gdf_roads.geometry.apply(lambda x: (round(x.coords[-1][0], 6), round(x.coords[-1][1], 6)))

all_nodes = pd.concat([gdf_roads['u_coord'], gdf_roads['v_coord']]).unique()
node_map = {coord: i for i, coord in enumerate(all_nodes)}

gdf_roads['u'] = gdf_roads['u_coord'].map(node_map)
gdf_roads['v'] = gdf_roads['v_coord'].map(node_map)
gdf_roads['key'] = gdf_roads.groupby(['u', 'v']).cumcount()

node_rows = [{'osmid': i, 'geometry': Point(coord), 'x': coord[0], 'y': coord[1]} for coord, i in node_map.items()]
gdf_nodes = gpd.GeoDataFrame(node_rows, crs=gdf_roads.crs).set_index('osmid')
gdf_roads = gdf_roads.set_index(['u', 'v', 'key'])
gdf_roads = gdf_roads.drop(columns=['u_coord', 'v_coord'])

# --- 4. Create & Project Graph ---
print("4. Creating & Projecting Graph...")
G = ox.graph_from_gdfs(gdf_nodes, gdf_roads)
del gdf_nodes, gdf_roads, node_rows, node_map
gc.collect()

# Repair Connectivity
G = G.to_undirected()
G = G.to_directed()

# Project to UTM
G_proj = ox.project_graph(G)
del G
gc.collect()

# NULL ISLAND NUKE (Node Level)
# Explicitly delete any node that is "Too South" (Y < 4,000,000m) or "Too West"
print("   Purging artifacts...")
nodes_to_remove = [n for n, data in G_proj.nodes(data=True) if data['y'] < 4000000]
if len(nodes_to_remove) > 0:
    print(f"   🚨 REMOVING {len(nodes_to_remove)} ARTIFACT NODES (Zero-Coordinates)!")
    G_proj.remove_nodes_from(nodes_to_remove)

print("   Consolidating Intersections...")
G_fixed = ox.consolidate_intersections(G_proj, tolerance=15, rebuild_graph=True, dead_ends=False)
del G_proj
gc.collect()

# --- 5. Calculate Physics (Optimized Logic) ---
print("5. Calculating Physics...")

for u, v, k, data in G_fixed.edges(keys=True, data=True):
    # HELPER: Extract value from list if necessary
    def get_val(key, default):
        val = data.get(key, default)
        if isinstance(val, list):
            clean_vals = [v for v in val if str(v).lower() != 'unknown']
            return clean_vals[0] if clean_vals else val[0]
        return val

    # Length
    if 'geometry' in data:
        length = data['geometry'].length
    else:
        length = float(get_val('length', 0))

    # Speed
    speed = float(get_val('safe_speed', 50))

    # --- TUNED PENALTY LOGIC ---
    status = str(get_val('PAVSTATUS', 'Unknown'))
    surface = str(get_val('PAVSURF', 'Unknown'))
    r_class = str(get_val('ROADCLASS', 'Unknown'))

    # 1. OPTIMISTIC PAVING: 'Unknown' is assumed PAVED.
    # Only penalize explicit bad surfaces.
    bad_surfaces = ['Unpaved', 'Loose', 'Rough', 'Gravel', 'Dirt', 'Earth']
    if status == 'Unpaved' or surface in bad_surfaces:
        speed *= 0.6  # 40% penalty for gravel

    # 2. Ferry Logic
    if r_class == 'Ferry' or surface == 'Water':
        speed = 10.0

    # Sanity Floor
    if speed < 1: speed = 10.0

    # Time Calc
    time_min = ((length / 1000) / speed) * 60

    if r_class == 'Ferry':
        time_min += 30.0

    # Update Attributes
    data.clear() 
    data['length'] = round(length, 2)
    data['travel_time'] = round(time_min, 3)
    data['speed_kph'] = round(speed, 1)

    # Keep Metadata for Auditing
    data['ROADCLASS'] = r_class
    data['PAVSURF'] = surface

# --- 6. Save ---
outfile = "BC_GOLDEN_REPAIRED.graphml"
print(f"6. Saving Optimized Graph to '{outfile}'...")
ox.save_graphml(G_fixed, filepath=outfile)

print("-" * 40)
print(f"✅ DONE. Graph Nodes: {len(G_fixed.nodes):,}, Edges: {len(G_fixed.edges):,}")
print("-" * 40)


# A new Production run with adjusted parameters:

# In[ ]:


import osmnx as ox
import networkx as nx
import pandas as pd
import geopandas as gpd
import numpy as np
import time
import psutil
import os
import sys
import folium
from IPython.display import display
from multiprocessing import Pool, cpu_count

# --- Configuration ---
CHUNK_SIZE = 100        
TOTAL_TRIPS = 1000      
GRAPH_FILE = "BC_GOLDEN_REPAIRED.graphml" 
NUM_CORES = 3          

print(f"🏁 PRODUCTION START. RAM: {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MB")

# --- 1. Load Graph ---
print("1. Loading High-Fidelity Graph...")
G = ox.load_graphml(GRAPH_FILE) 
target_crs = G.graph['crs']
print(f"   Graph Ready. Nodes: {len(G.nodes):,}, Edges: {len(G.edges):,}")

# --- 2. Generate Data (Urban) ---
print(f"2. Generating {TOTAL_TRIPS} Urban Mock Trips...")
np.random.seed(42)
north, south = 49.35, 49.00
east, west = -121.90, -123.25

orig_x = np.random.uniform(east, west, TOTAL_TRIPS)
orig_y = np.random.uniform(south, north, TOTAL_TRIPS)
dest_x = np.random.uniform(east, west, TOTAL_TRIPS)
dest_y = np.random.uniform(south, north, TOTAL_TRIPS)

print("   Projecting inputs...")
gdf_orig = gpd.GeoDataFrame(geometry=gpd.points_from_xy(orig_x, orig_y), crs="EPSG:4326").to_crs(target_crs)
gdf_dest = gpd.GeoDataFrame(geometry=gpd.points_from_xy(dest_x, dest_y), crs="EPSG:4326").to_crs(target_crs)

# --- 3. Pre-Snap ---
print("3. Pre-Snapping Coordinates...")
snap_start = time.time()
orig_nodes = ox.nearest_nodes(G, gdf_orig.geometry.x, gdf_orig.geometry.y)
dest_nodes = ox.nearest_nodes(G, gdf_dest.geometry.x, gdf_dest.geometry.y)
print(f"   Snapping complete in {time.time()-snap_start:.2f}s")

trips_df = pd.DataFrame({
    'trip_id': range(TOTAL_TRIPS),
    'orig_node': orig_nodes,
    'dest_node': dest_nodes
})

# --- 4. Worker Function ---
def calculate_chunk(indices):
    subset = trips_df.iloc[indices]
    try:
        routes = ox.shortest_path(G, subset['orig_node'], subset['dest_node'], weight='travel_time')
    except Exception:
        routes = [None] * len(subset)

    dist_list = []
    time_list = []
    valid_routes = []

    for route in routes:
        if route is None:
            dist_list.append(np.nan)
            time_list.append(np.nan)
            valid_routes.append(None)
        else:
            d = 0.0
            t = 0.0
            for u, v in zip(route[:-1], route[1:]):
                edges = G[u][v]
                best_key = min(edges, key=lambda k: edges[k].get('travel_time', float('inf')))
                edge_data = edges[best_key]
                d += float(edge_data.get('length', 0))
                t += float(edge_data.get('travel_time', 0))
            dist_list.append(d / 1000)
            time_list.append(t)
            valid_routes.append(route)

    return indices, dist_list, time_list, valid_routes

# --- 5. Execution ---
print(f"4. Running Simulation on {NUM_CORES} Cores...")
print("-" * 100)

global_start = time.time()
all_distances = [np.nan] * TOTAL_TRIPS
all_times = [np.nan] * TOTAL_TRIPS
longest_route_data = {'dist': -1, 'route': None, 'id': -1}

indices = list(range(TOTAL_TRIPS))
chunks = [indices[i:i + CHUNK_SIZE] for i in range(0, len(indices), CHUNK_SIZE)]

with Pool(processes=NUM_CORES) as pool:
    completed = 0
    for idx_list, d_list, t_list, r_list in pool.imap_unordered(calculate_chunk, chunks):
        for i, idx in enumerate(idx_list):
            dist = d_list[i]
            if dist is not np.nan:
                all_distances[idx] = dist
                all_times[idx] = t_list[i]
                if dist > longest_route_data['dist']:
                    longest_route_data['dist'] = dist
                    longest_route_data['route'] = r_list[i]
                    longest_route_data['id'] = idx

        completed += len(idx_list)
        elapsed = time.time() - global_start
        rate = completed / elapsed if elapsed > 0 else 0
        percent = completed / TOTAL_TRIPS
        remaining = TOTAL_TRIPS - completed
        eta = remaining / rate if rate > 0 else 0
        bar = '█' * int(30 * percent) + '-' * (30 - int(30 * percent))
        sys.stdout.write(f"\r|{bar}| {percent:.1%} | {completed}/{TOTAL_TRIPS} | ETA: {eta:.0f}s | {int(rate)} routes/s")
        sys.stdout.flush()

print("\n" + "-" * 100)

# --- 6. Report ---
trips_df['distance_km'] = all_distances
trips_df['travel_time_min'] = all_times
successful = trips_df['distance_km'].notna().sum()

print(f"COMPLETE. Total Time: {time.time()-global_start:.1f}s")
print(f"Success Rate: {successful}/{TOTAL_TRIPS} ({(successful/TOTAL_TRIPS)*100:.1f}%)")
print("\n--- STATISTICS (Units: KM and Minutes) ---")
print(trips_df[['distance_km', 'travel_time_min']].describe().round(2))

# --- 7. ROUTE AUDITOR ---
def audit_and_plot(G_graph, route, title="Route"):
    print(f"\n🕵️ AUDITING: {title}...")

    segments = list(zip(route[:-1], route[1:]))
    print(f"\n   --- DECISION LOG (Sample Segments) ---")
    print(f"   {'CLASS':<15} | {'STATUS':<10} | {'SURFACE':<10} | {'SPEED':<8} | {'DIST (m)':<10} | {'TIME (min)':<10}")
    print("   " + "-" * 80)

    indices_to_show = list(range(0, 5)) + \
                      list(range(len(segments)//2 - 2, len(segments)//2 + 3)) + \
                      list(range(len(segments)-5, len(segments)))
    shown = set()

    for i, (u, v) in enumerate(segments):
        if i in indices_to_show and i not in shown:
            shown.add(i)
            edges = G_graph[u][v]
            best_key = min(edges, key=lambda k: edges[k].get('travel_time', float('inf')))
            data = edges[best_key]

            r_cls = str(data.get('ROADCLASS', 'Unknown'))
            stat = str(data.get('PAVSTATUS', 'Unknown'))
            surf = str(data.get('PAVSURF', 'Unknown'))
            spd = float(data.get('speed_kph', 0))
            ln = float(data.get('length', 0))
            tm = float(data.get('travel_time', 0))

            print(f"   {r_cls[:15]:<15} | {stat[:10]:<10} | {surf[:10]:<10} | {spd:<8.1f} | {ln:<10.1f} | {tm:<10.2f}")
        elif i == 6 and len(segments) > 15:
            print("   ... (skipping intermediate segments) ...")

    print(f"\nGenerating Map for: {title}...")
    route_nodes = [G_graph.nodes[n] for n in route]
    gdf_nodes = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy([n['x'] for n in route_nodes], [n['y'] for n in route_nodes]),
        crs=G_graph.graph['crs']
    ).to_crs(epsg=4326)

    coords = [(p.y, p.x) for p in gdf_nodes.geometry]
    m = folium.Map(location=coords[len(coords)//2], zoom_start=11, tiles='OpenStreetMap')
    folium.PolyLine(coords, color="blue", weight=5, opacity=0.7, tooltip=title).add_to(m)
    folium.Marker(coords[0], popup="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(coords[-1], popup="End", icon=folium.Icon(color="red")).add_to(m)
    display(m)

if longest_route_data['route']:
    long_id = longest_route_data['id']
    dist = longest_route_data['dist']
    print(f"\n🏆 Longest Urban Route (ID {long_id}): {dist:.1f} km")
    audit_and_plot(G, longest_route_data['route'], title=f"Trip {long_id}")
else:
    print("\nNo routes found to plot.")


# 5 avg trips again:

# In[4]:


import osmnx as ox
import networkx as nx
import pandas as pd
import geopandas as gpd
import numpy as np
import time
import psutil
import os
import sys
import ipywidgets as widgets
from ipyleaflet import Map, Polyline, Marker, AwesomeIcon, basemaps
from IPython.display import display
from multiprocessing import Pool, cpu_count

# --- Configuration ---
CHUNK_SIZE = 100        
TOTAL_TRIPS = 1000      
GRAPH_FILE = "BC_GOLDEN_REPAIRED.graphml" 
NUM_CORES = 3          

print(f"🏁 ANALYTICS START. RAM: {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MB")

# --- 1. Load Graph ---
print("1. Loading High-Fidelity Graph...")
G = ox.load_graphml(GRAPH_FILE) 
target_crs = G.graph['crs']
print(f"   Graph Ready. Nodes: {len(G.nodes):,}, Edges: {len(G.edges):,}")

# --- 2. Generate Data (Urban Focused) ---
print(f"2. Generating {TOTAL_TRIPS} Urban Mock Trips...")
np.random.seed(42)
# Bounds: Metro Vancouver / Fraser Valley 
north, south = 49.35, 49.00
east, west = -121.90, -123.25

orig_x = np.random.uniform(east, west, TOTAL_TRIPS)
orig_y = np.random.uniform(south, north, TOTAL_TRIPS)
dest_x = np.random.uniform(east, west, TOTAL_TRIPS)
dest_y = np.random.uniform(south, north, TOTAL_TRIPS)

print("   Projecting inputs...")
gdf_orig = gpd.GeoDataFrame(geometry=gpd.points_from_xy(orig_x, orig_y), crs="EPSG:4326").to_crs(target_crs)
gdf_dest = gpd.GeoDataFrame(geometry=gpd.points_from_xy(dest_x, dest_y), crs="EPSG:4326").to_crs(target_crs)

# --- 3. Pre-Snap ---
print("3. Pre-Snapping Coordinates...")
orig_nodes = ox.nearest_nodes(G, gdf_orig.geometry.x, gdf_orig.geometry.y)
dest_nodes = ox.nearest_nodes(G, gdf_dest.geometry.x, gdf_dest.geometry.y)

trips_df = pd.DataFrame({
    'trip_id': range(TOTAL_TRIPS),
    'orig_node': orig_nodes,
    'dest_node': dest_nodes
})

# --- 4. Worker Function ---
def calculate_chunk(indices):
    subset = trips_df.iloc[indices]
    try:
        routes = ox.shortest_path(G, subset['orig_node'], subset['dest_node'], weight='travel_time')
    except Exception:
        routes = [None] * len(subset)

    dist_list = []
    time_list = []

    for route in routes:
        if route is None:
            dist_list.append(np.nan)
            time_list.append(np.nan)
        else:
            d = 0.0
            t = 0.0
            for u, v in zip(route[:-1], route[1:]):
                edges = G[u][v]
                best_key = min(edges, key=lambda k: edges[k].get('travel_time', float('inf')))
                edge_data = edges[best_key]
                d += float(edge_data.get('length', 0))
                t += float(edge_data.get('travel_time', 0))
            dist_list.append(d / 1000) # km
            time_list.append(t)        # min

    return indices, dist_list, time_list

# --- 5. Execution ---
print(f"4. Running Simulation on {NUM_CORES} Cores...")
global_start = time.time()
all_distances = [np.nan] * TOTAL_TRIPS
all_times = [np.nan] * TOTAL_TRIPS

indices = list(range(TOTAL_TRIPS))
chunks = [indices[i:i + CHUNK_SIZE] for i in range(0, len(indices), CHUNK_SIZE)]

with Pool(processes=NUM_CORES) as pool:
    for idx_list, d_list, t_list in pool.imap_unordered(calculate_chunk, chunks):
        for i, idx in enumerate(idx_list):
            all_distances[idx] = d_list[i]
            all_times[idx] = t_list[i]

# --- 6. Report & Selection ---
trips_df['distance_km'] = all_distances
trips_df['travel_time_min'] = all_times
successful = trips_df.dropna()

print(f"COMPLETE. Total Time: {time.time()-global_start:.1f}s")
print("\n--- STATISTICS ---")
print(successful[['distance_km', 'travel_time_min']].describe().round(2))

# Select 5 Representative Trips
# Min, Q1 (25%), Median (50%), Q3 (75%), Max
valid_trips = successful.sort_values('distance_km')
indices_to_audit = [
    valid_trips.index[0], # Min
    valid_trips.index[int(len(valid_trips)*0.25)], # Q1
    valid_trips.index[int(len(valid_trips)*0.50)], # Median
    valid_trips.index[int(len(valid_trips)*0.75)], # Q3
    valid_trips.index[-1] # Max
]
labels = ["Shortest", "25th Percentile (Q1)", "Median", "75th Percentile (Q3)", "Longest"]

# --- 7. DEEP AUDIT FUNCTION ---
def audit_trip(trip_idx, label):
    row = trips_df.loc[trip_idx]
    orig = int(row['orig_node'])
    dest = int(row['dest_node'])

    print(f"\n{'='*80}")
    print(f"🔍 AUDIT: {label} (Trip ID {trip_idx})")
    print(f"   Total Distance: {row['distance_km']:.2f} km")
    print(f"   Total Time:     {row['travel_time_min']:.2f} min")
    print(f"{'='*80}")

    # Re-calculate specific route
    route = ox.shortest_path(G, orig, dest, weight='travel_time')
    if not route:
        print("Error: Could not reproduce route.")
        return

    # Print Step-by-Step Logic
    print(f"\n   --- ROUTE DECISION LOG ---")
    print(f"   {'ROAD CLASS':<20} | {'SURFACE':<10} | {'SPEED':<8} | {'DIST (m)':<10} | {'COST (min)':<10}")
    print("   " + "-" * 75)

    # Sample logic: Show first 5, middle 5, last 5 edges
    segments = list(zip(route[:-1], route[1:]))
    idxs = list(range(0, 5)) + \
           list(range(len(segments)//2 - 2, len(segments)//2 + 3)) + \
           list(range(len(segments)-5, len(segments)))

    shown = set()
    for i, (u, v) in enumerate(segments):
        if i in idxs and i not in shown:
            shown.add(i)
            # Inspect Edge Attributes
            edges = G[u][v]
            best_key = min(edges, key=lambda k: edges[k].get('travel_time', float('inf')))
            data = edges[best_key]

            cls = str(data.get('ROADCLASS', 'N/A'))
            surf = str(data.get('PAVSURF', 'N/A'))
            spd = float(data.get('speed_kph', 0))
            ln = float(data.get('length', 0))
            cost = float(data.get('travel_time', 0))

            print(f"   {cls[:20]:<20} | {surf[:10]:<10} | {spd:<8.1f} | {ln:<10.1f} | {cost:<10.2f}")
        elif i == 6 and len(segments) > 15:
            print("   ... (skipping intermediate segments) ...")

    # Interactive Map
    print(f"\n   Generating Map...")
    route_nodes = [G.nodes[n] for n in route]
    gdf_nodes = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy([n['x'] for n in route_nodes], [n['y'] for n in route_nodes]),
        crs=G.graph['crs']
    ).to_crs(epsg=4326)

    path_coords = [(p.y, p.x) for p in gdf_nodes.geometry]
    m = Map(basemap=basemaps.OpenStreetMap.Mapnik, center=path_coords[len(path_coords)//2], zoom=11, layout=widgets.Layout(height='400px'))

    line = Polyline(locations=path_coords, color="blue", fill=False, weight=5)
    m.add_layer(line)
    m.add_layer(Marker(location=path_coords[0], title="Start"))
    m.add_layer(Marker(location=path_coords[-1], title="End"))

    display(m)

# Run Audit for selected trips
for idx, lbl in zip(indices_to_audit, labels):
    audit_trip(idx, lbl)

