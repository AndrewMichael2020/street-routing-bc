import osmnx as ox
import networkx as nx
import geopandas as gpd
import pandas as pd
import numpy as np
import gc
import psutil
import os
from shapely.geometry import Point, LineString
from shapely import make_valid
from shapely.validation import explain_validity

print("🏁 FACTORY v12 (Enhanced Preprocessing & Validation) STARTING...")

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
    # Load necessary columns including ROADJURIS, TRAFFICDIR, and IDs
    keep_cols = ['geometry', 'SPEED', 'ROADCLASS', 'PAVSURF', 'PAVSTATUS', 'ROADJURIS', 'TRAFFICDIR', 'NID', 'ROADSEGID']
    gdf_roads = gpd.read_file(gpkg_filename, layer=layer_name)
    
    # Prune immediately
    existing_cols = [c for c in keep_cols if c in gdf_roads.columns]
    missing_cols = [c for c in keep_cols if c not in gdf_roads.columns]
    gdf_roads = gdf_roads[existing_cols]
    
    # Diagnostic output
    print(f"   ✅ Loaded columns: {existing_cols}")
    if missing_cols:
        print(f"   ⚠️  Missing columns: {missing_cols}")
    
    # Confirm CRS
    print(f"   📍 Input CRS: {gdf_roads.crs}")
    if str(gdf_roads.crs) == 'EPSG:4617':
        print("   ⚠️  Data is in geographic coordinates (EPSG:4617)")
        print("   ➡️  Will reproject to EPSG:3005 (BC Albers) for metric calculations")
    
except Exception as e:
    print(f"❌ Error loading file: {e}")
    exit()

initial_len = len(gdf_roads)
print(f"   Loaded {initial_len} rows. RAM: {get_ram():.1f} MB")

# --- 2. QA & Sanitization ---
print("2. QA & Sanitization...")

# A. Validate and Repair Geometries
print("   A. Geometry Validation & Repair...")
invalid_geoms = ~gdf_roads.geometry.is_valid
invalid_count = invalid_geoms.sum()
if invalid_count > 0:
    print(f"   ⚠️  Found {invalid_count} invalid geometries - repairing with make_valid()")
    # Show examples of invalid geometries
    invalid_sample = gdf_roads[invalid_geoms].head(3)
    for idx, row in invalid_sample.iterrows():
        print(f"      Example: {explain_validity(row.geometry)}")
    # Repair using make_valid
    gdf_roads.loc[invalid_geoms, 'geometry'] = gdf_roads.loc[invalid_geoms, 'geometry'].apply(make_valid)
    # Recheck validity
    still_invalid = ~gdf_roads.geometry.is_valid
    if still_invalid.sum() > 0:
        print(f"   ⚠️  {still_invalid.sum()} geometries still invalid after repair - removing them")
        gdf_roads = gdf_roads[gdf_roads.geometry.is_valid]
    else:
        print(f"   ✅ All geometries repaired successfully")
else:
    print(f"   ✅ All {len(gdf_roads)} geometries are valid")

# Check for empty geometries
empty_geoms = gdf_roads.geometry.is_empty
empty_count = empty_geoms.sum()
if empty_count > 0:
    print(f"   ⚠️  Found {empty_count} empty geometries - removing them")
    gdf_roads = gdf_roads[~empty_geoms]
else:
    print(f"   ✅ No empty geometries found")

# Check for null geometries
null_geoms = gdf_roads.geometry.isna()
null_count = null_geoms.sum()
if null_count > 0:
    print(f"   ⚠️  Found {null_count} null geometries - removing them")
    gdf_roads = gdf_roads[~null_geoms]

# Filter out massive artifacts (> 2 degrees / ~220km in geographic coords)
print("   B. Filtering artifacts by length...")
before_filter = len(gdf_roads)
gdf_roads = gdf_roads[gdf_roads.geometry.length < 2.0]
print(f"   Removed {before_filter - len(gdf_roads)} segments with length > 2 degrees")

# Filter out tiny artifacts (< 1 meter in geographic coords ≈ 0.00001 degrees)
before_filter = len(gdf_roads)
gdf_roads = gdf_roads[gdf_roads.geometry.length > 0.00001] 
print(f"   Removed {before_filter - len(gdf_roads)} segments with length < 0.00001 degrees")

# Check for zero-length geometries after filtering
zero_length = gdf_roads.geometry.length == 0
zero_count = zero_length.sum()
if zero_count > 0:
    print(f"   ⚠️  Found {zero_count} zero-length geometries - removing them")
    gdf_roads = gdf_roads[~zero_length]

# C. Spatial Filter (BC Bounding Box - Strict)
print("   C. Applying spatial filter for BC...")
before_filter = len(gdf_roads)
gdf_roads = gdf_roads.cx[-140:-110, 48:62]
print(f"   Removed {before_filter - len(gdf_roads)} segments outside BC bounding box")

# D. REPROJECT TO BC ALBERS (EPSG:3005) FOR METRIC CALCULATIONS
print("   D. Reprojecting to BC Albers (EPSG:3005)...")
original_crs = gdf_roads.crs
if gdf_roads.crs.to_epsg() != 3005:
    gdf_roads = gdf_roads.to_crs('EPSG:3005')
    print(f"   ✅ Reprojected from {original_crs} to EPSG:3005")
    print(f"   📍 New CRS: {gdf_roads.crs} (metric - meters)")
else:
    print(f"   ✅ Already in EPSG:3005")

# E. Compute and inspect segment lengths in meters
print("   E. Computing segment lengths (post-projection)...")
gdf_roads['length_m'] = gdf_roads.geometry.length
length_stats = gdf_roads['length_m'].describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
print(f"   Length distribution (meters):")
print(f"      Min:     {length_stats['min']:>12.2f} m")
print(f"      1%:      {length_stats['1%']:>12.2f} m")
print(f"      5%:      {length_stats['5%']:>12.2f} m")
print(f"      25%:     {length_stats['25%']:>12.2f} m")
print(f"      Median:  {length_stats['50%']:>12.2f} m")
print(f"      75%:     {length_stats['75%']:>12.2f} m")
print(f"      95%:     {length_stats['95%']:>12.2f} m")
print(f"      99%:     {length_stats['99%']:>12.2f} m")
print(f"      Max:     {length_stats['max']:>12.2f} m")
print(f"      Mean:    {length_stats['mean']:>12.2f} m")

# Check for absurd lengths (e.g., > 100km = 100,000m)
absurd_length = gdf_roads['length_m'] > 100000
absurd_count = absurd_length.sum()
if absurd_count > 0:
    print(f"   ⚠️  Found {absurd_count} segments with length > 100km - these may be errors")
    # Show examples
    absurd_sample = gdf_roads[absurd_length][['ROADCLASS', 'length_m']].head(5)
    print(f"      Examples:\n{absurd_sample}")
    # Optionally remove them
    gdf_roads = gdf_roads[~absurd_length]
    print(f"   Removed {absurd_count} segments with absurd lengths")

# F. ATTRIBUTE CLEANING
print("   F. Normalizing attribute values...")
text_cols = ['ROADCLASS', 'PAVSURF', 'PAVSTATUS', 'ROADJURIS', 'TRAFFICDIR']
for col in text_cols:
    if col in gdf_roads.columns:
        gdf_roads[col] = gdf_roads[col].astype(str).str.title().replace({'None': 'Unknown', 'Nan': 'Unknown'})

# Normalize categorical variants
if 'TRAFFICDIR' in gdf_roads.columns:
    # Map variants to canonical values
    trafficdir_mapping = {
        'Both': 'Both Directions',
        'Bidirectional': 'Both Directions',
        'Positive': 'Same Direction',
        'Forward': 'Same Direction',
        'Negative': 'Opposite Direction',
        'Reverse': 'Opposite Direction',
    }
    gdf_roads['TRAFFICDIR'] = gdf_roads['TRAFFICDIR'].replace(trafficdir_mapping)
    print(f"   ✅ Normalized TRAFFICDIR values")

# G. DATA QUALITY DIAGNOSTICS
print("   G. Data Quality Check:")
for col in ['TRAFFICDIR', 'PAVSURF', 'ROADCLASS', 'SPEED']:
    if col in gdf_roads.columns:
        total = len(gdf_roads)
        if col == 'SPEED':
            # For SPEED, count valid (> 0) values
            valid_count = (pd.to_numeric(gdf_roads[col], errors='coerce') > 0).sum()
            missing_count = total - valid_count
        else:
            unknown_count = (gdf_roads[col] == 'Unknown').sum()
            valid_count = total - unknown_count
            missing_count = unknown_count
        valid_pct = (valid_count / total) * 100 if total > 0 else 0
        print(f"     {col:<15}: {valid_count:>7,} valid ({valid_pct:>5.1f}%), {missing_count:>7,} missing/unknown")
        # Show top values for non-numeric columns
        if col != 'SPEED' and valid_count > 0:
            top_vals = gdf_roads[gdf_roads[col] != 'Unknown'][col].value_counts().head(3)
            print(f"       Top values: {', '.join([f'{v}: {c:,}' for v, c in top_vals.items()])}")

# H. Check for duplicate segment IDs
print("   H. Checking for duplicate IDs...")
if 'ROADSEGID' in gdf_roads.columns:
    dup_roadsegid = gdf_roads['ROADSEGID'].duplicated()
    dup_count = dup_roadsegid.sum()
    if dup_count > 0:
        print(f"   ⚠️  Found {dup_count} duplicate ROADSEGID values")
        # Show examples
        dup_ids = gdf_roads[dup_roadsegid]['ROADSEGID'].head(5).tolist()
        print(f"      Examples: {dup_ids}")
    else:
        print(f"   ✅ All ROADSEGID values are unique")

if 'NID' in gdf_roads.columns:
    dup_nid = gdf_roads['NID'].duplicated()
    dup_count = dup_nid.sum()
    if dup_count > 0:
        print(f"   ⚠️  Found {dup_count} duplicate NID values")
    else:
        print(f"   ✅ All NID values are unique")

# I. INFER MISSING VALUES
print("   I. Inferring missing values...")

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

# E. SPEED LOGIC (BOOSTED) with validation
print("   J. Validating and normalizing SPEED values...")
gdf_roads['SPEED'] = pd.to_numeric(gdf_roads['SPEED'], errors='coerce').fillna(-1)

# Validate SPEED values - clip unrealistic speeds
# Highway speeds in BC: max 110 km/h (with some margin for data entry errors)
# Min reasonable speed: 10 km/h (for ferry, service lanes)
invalid_speed_mask = (gdf_roads['SPEED'] > 0) & ((gdf_roads['SPEED'] > 130) | (gdf_roads['SPEED'] < 5))
invalid_speed_count = invalid_speed_mask.sum()
if invalid_speed_count > 0:
    print(f"   ⚠️  Found {invalid_speed_count} segments with invalid SPEED values (>130 or <5)")
    # Show examples
    speed_examples = gdf_roads[invalid_speed_mask][['ROADCLASS', 'SPEED']].head(5)
    print(f"      Examples:\n{speed_examples}")
    # Clip speeds to reasonable range
    gdf_roads.loc[(gdf_roads['SPEED'] > 130), 'SPEED'] = -1  # Mark as unknown
    gdf_roads.loc[(gdf_roads['SPEED'] > 0) & (gdf_roads['SPEED'] < 5), 'SPEED'] = 10  # Set minimum
    print(f"   ✅ Clipped invalid SPEED values")

# Speed Defaults for BC Roads
# Note: Most highways in BC are 90 km/h, with only Abbotsford-Hope section at 100 km/h
defaults = {
    'Freeway': 90,       # Most BC highways are 90 km/h
    'Expressway': 90,    # Most BC highways are 90 km/h
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

# Log speed imputation
imputed_count = (gdf_roads['SPEED'] <= 0).sum()
print(f"   Imputed SPEED for {imputed_count:,} segments based on ROADCLASS")

# Drop dirty column
gdf_roads = gdf_roads.drop(columns=['SPEED']) 
print(f"   K. Total segments after QA: {len(gdf_roads):,} (removed {initial_len - len(gdf_roads):,})")
gc.collect()

# --- 3. Build Topology ---
print("3. Building Topology...")
# Use 1 decimal place precision (0.1m = 10cm) for BC Albers coordinates
# This is sufficient for road network topology while avoiding over-merging
gdf_roads['u_coord'] = gdf_roads.geometry.apply(lambda x: (round(x.coords[0][0], 1), round(x.coords[0][1], 1)))
gdf_roads['v_coord'] = gdf_roads.geometry.apply(lambda x: (round(x.coords[-1][0], 1), round(x.coords[-1][1], 1)))

# Detect potential duplicate segments
print("   Checking for duplicate/overlapping segments...")
coord_pairs = gdf_roads[['u_coord', 'v_coord']].apply(lambda row: tuple(sorted([row['u_coord'], row['v_coord']])), axis=1)
dup_segments = coord_pairs.duplicated()
dup_count = dup_segments.sum()
if dup_count > 0:
    print(f"   ⚠️  Found {dup_count} potentially duplicate segments (same start/end coords)")
    # Keep all duplicates for now (might be parallel roads, multi-lane highways)
    print(f"   ➡️  Keeping duplicates (may represent parallel lanes/roads)")
else:
    print(f"   ✅ No duplicate segments detected")

all_nodes = pd.concat([gdf_roads['u_coord'], gdf_roads['v_coord']]).unique()
node_map = {coord: i for i, coord in enumerate(all_nodes)}

gdf_roads['u'] = gdf_roads['u_coord'].map(node_map)
gdf_roads['v'] = gdf_roads['v_coord'].map(node_map)
gdf_roads['key'] = gdf_roads.groupby(['u', 'v']).cumcount()

node_rows = [{'osmid': i, 'geometry': Point(coord), 'x': coord[0], 'y': coord[1]} for coord, i in node_map.items()]
gdf_nodes = gpd.GeoDataFrame(node_rows, crs=gdf_roads.crs).set_index('osmid')
gdf_roads = gdf_roads.set_index(['u', 'v', 'key'])

# Drop temporary coordinate columns but keep length_m for later
gdf_roads = gdf_roads.drop(columns=['u_coord', 'v_coord'])

print(f"   Created topology with {len(gdf_nodes):,} nodes and {len(gdf_roads):,} edges")

# --- 4. Create Graph (Already in EPSG:3005) ---
print("4. Creating Graph (already in BC Albers EPSG:3005)...")
G = ox.graph_from_gdfs(gdf_nodes, gdf_roads)
print(f"   Graph CRS: {G.graph.get('crs', 'Not set')}")
# Set CRS explicitly to BC Albers since we already projected
G.graph['crs'] = 'EPSG:3005'
print(f"   ✅ Graph created with {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
del gdf_nodes, gdf_roads, node_rows, node_map
gc.collect()

# --- 5. Handle Directionality ---
print("5. Handling directionality for one-way roads...")
# Create a directed graph and add reverse edges only for bidirectional roads
G_directed = G.to_directed()

# For a cleaner approach, rebuild the graph with proper directionality
G_fixed_temp = nx.MultiDiGraph()
G_fixed_temp.graph.update(G_directed.graph)

# Add nodes
for node, data in G_directed.nodes(data=True):
    G_fixed_temp.add_node(node, **data)

# Add edges with proper directionality based on TRAFFICDIR
oneway_forward = 0
oneway_reverse = 0
bidirectional = 0

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
        bidirectional += 1
    elif traffic_dir in ['Same Direction', 'Positive']:
        # One-way forward: only u->v
        G_fixed_temp.add_edge(u, v, k, **data)
        oneway_forward += 1
    elif traffic_dir in ['Opposite Direction', 'Negative']:
        # One-way reverse: only v->u
        G_fixed_temp.add_edge(v, u, k, **data)
        oneway_reverse += 1
    else:
        # Default to bidirectional for unknown patterns
        G_fixed_temp.add_edge(u, v, k, **data)
        reverse_data = data.copy()
        if 'geometry' in reverse_data:
            # Reverse the geometry for the reverse edge
            coords = list(reverse_data['geometry'].coords)
            reverse_data['geometry'] = LineString(coords[::-1])
        G_fixed_temp.add_edge(v, u, k, **reverse_data)
        bidirectional += 1

print(f"   Directionality summary:")
print(f"      Bidirectional: {bidirectional:,}")
print(f"      One-way forward: {oneway_forward:,}")
print(f"      One-way reverse: {oneway_reverse:,}")

del G_directed
gc.collect()
G_proj = G_fixed_temp
del G_fixed_temp
gc.collect()

# --- 6. Clean up artifacts ---
# NULL ISLAND NUKE (Node Level)
# Remove nodes that are artifacts (coordinates that shouldn't exist in BC Albers)
# BC Albers valid range: X: ~200,000-1,900,000, Y: ~300,000-1,700,000
print("6. Purging coordinate artifacts...")
nodes_to_remove = [n for n, data in G_proj.nodes(data=True) 
                   if data['y'] < 300000 or data['y'] > 1700000 or 
                      data['x'] < 200000 or data['x'] > 1900000]
if len(nodes_to_remove) > 0:
    print(f"   🚨 REMOVING {len(nodes_to_remove)} ARTIFACT NODES (out-of-bounds coordinates)!")
    G_proj.remove_nodes_from(nodes_to_remove)
else:
    print(f"   ✅ No artifact nodes found")

print("   Consolidating Intersections...")
# Check number of connected components - if too many, skip consolidation or use smaller tolerance
num_components = nx.number_weakly_connected_components(G_proj)
print(f"   Found {num_components} connected components")

if num_components > 50:
    print(f"   ⚠️  Too many components ({num_components}) - skipping consolidation to avoid timeout")
    print(f"   ➡️  Graph will have slightly more nodes but processing will complete")
    G_fixed = G_proj
    del G_proj
    gc.collect()
else:
    print(f"   Processing consolidation (this may take a few minutes)...")
    try:
        G_fixed = ox.consolidate_intersections(G_proj, tolerance=15, rebuild_graph=True, dead_ends=False)
        print(f"   ✅ Consolidation complete")
    except Exception as e:
        print(f"   ⚠️  Consolidation failed: {e}")
        print(f"   ➡️  Using unconsolidated graph")
        G_fixed = G_proj
    del G_proj
    gc.collect()

print(f"   Final graph: {G_fixed.number_of_nodes():,} nodes, {G_fixed.number_of_edges():,} edges")

# --- 7. Calculate Physics (Optimized Logic) ---
print("7. Calculating Physics (travel_time, length, speed)...")

for u, v, k, data in G_fixed.edges(keys=True, data=True):
    # HELPER: Extract value from list if necessary
    def get_val(key, default):
        val = data.get(key, default)
        if isinstance(val, list):
            clean_vals = [v for v in val if str(v).lower() != 'unknown']
            return clean_vals[0] if clean_vals else val[0]
        return val

    # Length - use pre-computed length_m if available, otherwise compute from geometry
    if 'length_m' in data:
        length = float(data['length_m'])
    elif 'geometry' in data:
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
    
    # Time Calc (length in meters, speed in km/h)
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

# --- 8. Save ---
outfile = "BC_GOLDEN_REPAIRED.graphml"
print(f"8. Saving Optimized Graph to '{outfile}'...")

# Final diagnostics
print("   Final Edge Attribute Quality:")
total_edges = G_fixed.number_of_edges()
trafficdir_known = sum(1 for u, v, k, d in G_fixed.edges(keys=True, data=True) if d.get('TRAFFICDIR', 'Unknown') != 'Unknown')
pavsurf_known = sum(1 for u, v, k, d in G_fixed.edges(keys=True, data=True) if d.get('PAVSURF', 'Unknown') != 'Unknown')
roadclass_known = sum(1 for u, v, k, d in G_fixed.edges(keys=True, data=True) if d.get('ROADCLASS', 'Unknown') != 'Unknown')

print(f"     TRAFFICDIR: {trafficdir_known:>7,}/{total_edges:>7,} ({(trafficdir_known/total_edges)*100:>5.1f}%)")
print(f"     PAVSURF:    {pavsurf_known:>7,}/{total_edges:>7,} ({(pavsurf_known/total_edges)*100:>5.1f}%)")
print(f"     ROADCLASS:  {roadclass_known:>7,}/{total_edges:>7,} ({(roadclass_known/total_edges)*100:>5.1f}%)")

# Compute final edge length statistics
edge_lengths = [d['length'] for u, v, k, d in G_fixed.edges(keys=True, data=True)]
if edge_lengths:
    edge_length_stats = pd.Series(edge_lengths).describe(percentiles=[0.5, 0.95, 0.99])
    print(f"\n   Final Edge Length Distribution (meters):")
    print(f"     Min:    {edge_length_stats['min']:>12.2f} m")
    print(f"     Median: {edge_length_stats['50%']:>12.2f} m")
    print(f"     95%:    {edge_length_stats['95%']:>12.2f} m")
    print(f"     99%:    {edge_length_stats['99%']:>12.2f} m")
    print(f"     Max:    {edge_length_stats['max']:>12.2f} m")
    print(f"     Mean:   {edge_length_stats['mean']:>12.2f} m")

ox.save_graphml(G_fixed, filepath=outfile)

print("-" * 40)
print(f"✅ DONE. Graph Nodes: {len(G_fixed.nodes):,}, Edges: {len(G_fixed.edges):,}")
print(f"   CRS: {G_fixed.graph.get('crs', 'Not set')}")
print("-" * 40)