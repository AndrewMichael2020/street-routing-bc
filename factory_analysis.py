import osmnx as ox
import networkx as nx
import geopandas as gpd
import pandas as pd
import numpy as np
import gc
import psutil
import os
from shapely.geometry import Point, LineString

print("🏁 FACTORY v11 (Highway Boost & Null-Island Nuke) STARTING...")

# Constants for road classification
MAJOR_ROAD_CLASSES = ['Freeway', 'Expressway', 'Arterial', 'Collector']
LOCAL_ROAD_CLASSES = ['Local', 'Collector', 'Resource', 'Ferry']

def get_ram():
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

print(f"   Initial RAM: {get_ram():.1f} MB")

# --- 1. Load Raw Data ---
print("1. Loading & Sanitizing NRN Data...")
gpkg_filename = "NRN_BC_14_0_GPKG_en.gpkg"
layer_name = "NRN_BC_14_0_ROADSEG"

try:
    # Load necessary columns including ROADJURIS and TRAFFICDIR
    keep_cols = ['geometry', 'SPEED', 'ROADCLASS', 'PAVSURF', 'PAVSTATUS', 'ROADJURIS', 'TRAFFICDIR']
    gdf_roads = gpd.read_file(gpkg_filename, layer=layer_name)
    
    # Prune immediately
    existing_cols = [c for c in keep_cols if c in gdf_roads.columns]
    missing_cols = [c for c in keep_cols if c not in gdf_roads.columns]
    gdf_roads = gdf_roads[existing_cols]
    
    # Diagnostic output
    print(f"   ✅ Loaded columns: {existing_cols}")
    if missing_cols:
        print(f"   ⚠️  Missing columns: {missing_cols}")
    
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
text_cols = ['ROADCLASS', 'PAVSURF', 'PAVSTATUS', 'ROADJURIS', 'TRAFFICDIR']
for col in text_cols:
    if col in gdf_roads.columns:
        gdf_roads[col] = gdf_roads[col].astype(str).str.title().replace({'None': 'Unknown', 'Nan': 'Unknown'})

# D. DATA QUALITY DIAGNOSTICS
print("   Data Quality Check:")
for col in ['TRAFFICDIR', 'PAVSURF', 'ROADCLASS']:
    if col in gdf_roads.columns:
        total = len(gdf_roads)
        unknown_count = (gdf_roads[col] == 'Unknown').sum()
        known_count = total - unknown_count
        known_pct = (known_count / total) * 100 if total > 0 else 0
        print(f"     {col:<15}: {known_count:>7,} known ({known_pct:>5.1f}%), {unknown_count:>7,} unknown")
        # Show top values
        if known_count > 0:
            top_vals = gdf_roads[gdf_roads[col] != 'Unknown'][col].value_counts().head(3)
            print(f"       Top values: {', '.join([f'{v}: {c:,}' for v, c in top_vals.items()])}")

# D2. INFER MISSING VALUES
print("   Inferring missing values...")

# Infer PAVSURF from PAVSTATUS if PAVSURF is Unknown but PAVSTATUS is known
if 'PAVSURF' in gdf_roads.columns and 'PAVSTATUS' in gdf_roads.columns:
    paved_mask = (gdf_roads['PAVSURF'] == 'Unknown') & (gdf_roads['PAVSTATUS'] == 'Paved')
    unpaved_mask = (gdf_roads['PAVSURF'] == 'Unknown') & (gdf_roads['PAVSTATUS'] == 'Unpaved')
    
    before_unknown = (gdf_roads['PAVSURF'] == 'Unknown').sum()
    gdf_roads.loc[paved_mask, 'PAVSURF'] = 'Paved'
    gdf_roads.loc[unpaved_mask, 'PAVSURF'] = 'Gravel'  # Assume unpaved means gravel
    after_unknown = (gdf_roads['PAVSURF'] == 'Unknown').sum()
    inferred = before_unknown - after_unknown
    print(f"     Inferred {inferred:,} PAVSURF values from PAVSTATUS")

# For remaining Unknown PAVSURF, assume paved for major roads
if 'PAVSURF' in gdf_roads.columns and 'ROADCLASS' in gdf_roads.columns:
    major_unknown_mask = (gdf_roads['PAVSURF'] == 'Unknown') & (gdf_roads['ROADCLASS'].isin(MAJOR_ROAD_CLASSES))
    
    before_unknown = (gdf_roads['PAVSURF'] == 'Unknown').sum()
    gdf_roads.loc[major_unknown_mask, 'PAVSURF'] = 'Paved'  # Assume major roads are paved
    after_unknown = (gdf_roads['PAVSURF'] == 'Unknown').sum()
    inferred = before_unknown - after_unknown
    print(f"     Inferred {inferred:,} PAVSURF values for major roads (assumed Paved)")

# For TRAFFICDIR, assume bidirectional for local roads, but leave highways as Unknown
# (safer to not infer directionality for divided highways)
if 'TRAFFICDIR' in gdf_roads.columns and 'ROADCLASS' in gdf_roads.columns:
    local_unknown_mask = (gdf_roads['TRAFFICDIR'] == 'Unknown') & (gdf_roads['ROADCLASS'].isin(LOCAL_ROAD_CLASSES))
    
    before_unknown = (gdf_roads['TRAFFICDIR'] == 'Unknown').sum()
    gdf_roads.loc[local_unknown_mask, 'TRAFFICDIR'] = 'Both Directions'  # Assume local roads are bidirectional
    after_unknown = (gdf_roads['TRAFFICDIR'] == 'Unknown').sum()
    inferred = before_unknown - after_unknown
    print(f"     Inferred {inferred:,} TRAFFICDIR values for local roads (assumed Both Directions)")
    print(f"     Note: {after_unknown:,} roads still have Unknown TRAFFICDIR (mostly highways - will be treated as bidirectional)")

# E. SPEED LOGIC (BOOSTED)
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

# Project to UTM FIRST (before directionality fixes)
# NOTE: ox.project_graph() doesn't project edge geometries, only nodes
# So we need to manually project edge geometries after projection
G_proj = ox.project_graph(G)
del G
gc.collect()

# Manually project all edge geometries to match the projected node coordinates
print("   Projecting edge geometries...")
target_crs = G_proj.graph['crs']

# Batch process geometries for better performance
edge_geometries = []
edge_keys = []
for u, v, k, data in G_proj.edges(keys=True, data=True):
    if 'geometry' in data:
        edge_geometries.append(data['geometry'])
        edge_keys.append((u, v, k))

if edge_geometries:
    # Project all geometries at once (more efficient than one-by-one)
    geom_gdf = gpd.GeoSeries(edge_geometries, crs='EPSG:4326')
    projected_geoms = geom_gdf.to_crs(target_crs)
    
    # Apply projected geometries back to edges
    for i, (u, v, k) in enumerate(edge_keys):
        G_proj[u][v][k]['geometry'] = projected_geoms.iloc[i]

# Handle Directionality AFTER projection
print("   Handling directionality for one-way roads...")
# Create a directed graph and add reverse edges only for bidirectional roads
G_directed = G_proj.to_directed()

# For a cleaner approach, rebuild the graph with proper directionality
G_fixed_temp = nx.MultiDiGraph()
G_fixed_temp.graph.update(G_directed.graph)

# Add nodes
for node, data in G_directed.nodes(data=True):
    G_fixed_temp.add_node(node, **data)

# Add edges with proper directionality based on TRAFFICDIR
for u, v, k, data in G_directed.edges(keys=True, data=True):
    traffic_dir = data.get('TRAFFICDIR', 'Unknown')
    if isinstance(traffic_dir, list):
        traffic_dir = traffic_dir[0] if traffic_dir else 'Unknown'
    traffic_dir = str(traffic_dir).title()
    
    # Handle different TRAFFICDIR cases
    if traffic_dir in ['Both Directions', 'Both', 'Unknown']:
        # Bidirectional: add both u->v and v->u
        G_fixed_temp.add_edge(u, v, k, **data)
        # Create reverse edge with reversed geometry
        reverse_data = data.copy()
        if 'geometry' in reverse_data:
            # Reverse the geometry for the reverse edge
            coords = list(reverse_data['geometry'].coords)
            reverse_data['geometry'] = LineString(coords[::-1])
        G_fixed_temp.add_edge(v, u, k, **reverse_data)
    elif traffic_dir in ['Same Direction', 'Positive']:
        # One-way forward: only u->v
        G_fixed_temp.add_edge(u, v, k, **data)
    elif traffic_dir in ['Opposite Direction', 'Negative']:
        # One-way reverse: only v->u
        G_fixed_temp.add_edge(v, u, k, **data)
    else:
        # Default to bidirectional for unknown patterns
        G_fixed_temp.add_edge(u, v, k, **data)
        reverse_data = data.copy()
        if 'geometry' in reverse_data:
            # Reverse the geometry for the reverse edge
            coords = list(reverse_data['geometry'].coords)
            reverse_data['geometry'] = LineString(coords[::-1])
        G_fixed_temp.add_edge(v, u, k, **reverse_data)

del G_directed
gc.collect()
G_proj = G_fixed_temp
del G_fixed_temp
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
    traffic_dir = str(get_val('TRAFFICDIR', 'Unknown'))
    
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
    data['TRAFFICDIR'] = traffic_dir

# --- 6. Save ---
outfile = "BC_GOLDEN_REPAIRED.graphml"
print(f"6. Saving Optimized Graph to '{outfile}'...")

# Final diagnostics
print("   Final Edge Attribute Quality:")
total_edges = G_fixed.number_of_edges()
trafficdir_known = sum(1 for u, v, k, d in G_fixed.edges(keys=True, data=True) if d.get('TRAFFICDIR', 'Unknown') != 'Unknown')
pavsurf_known = sum(1 for u, v, k, d in G_fixed.edges(keys=True, data=True) if d.get('PAVSURF', 'Unknown') != 'Unknown')
roadclass_known = sum(1 for u, v, k, d in G_fixed.edges(keys=True, data=True) if d.get('ROADCLASS', 'Unknown') != 'Unknown')

print(f"     TRAFFICDIR: {trafficdir_known:>7,}/{total_edges:>7,} ({(trafficdir_known/total_edges)*100:>5.1f}%)")
print(f"     PAVSURF:    {pavsurf_known:>7,}/{total_edges:>7,} ({(pavsurf_known/total_edges)*100:>5.1f}%)")
print(f"     ROADCLASS:  {roadclass_known:>7,}/{total_edges:>7,} ({(roadclass_known/total_edges)*100:>5.1f}%)")

ox.save_graphml(G_fixed, filepath=outfile)

print("-" * 40)
print(f"✅ DONE. Graph Nodes: {len(G_fixed.nodes):,}, Edges: {len(G_fixed.edges):,}")
print("-" * 40)