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
import webbrowser
from pathlib import Path
from multiprocessing import Pool, cpu_count

# --- Configuration ---
CHUNK_SIZE = 10         # Chunk size for parallel processing
TOTAL_TRIPS = 10        # 5 average routes + 5 edge routes
GRAPH_FILE = "BC_GOLDEN_REPAIRED.graphml" 
NUM_CORES = 3
AUDIT_ROUTES = 10       # Number of routes to audit in detail

# Constants for route generation
APPROX_KM_PER_DEGREE = 100.0  # Approximate conversion factor for BC latitude

# Route type labels for edge cases
EDGE_CASE_LABELS = [
    "Very Short (~5km)",
    "Long Distance (~80km)",
    "Cross-Region (~50km)",
    "Coastal Route",
    "Extreme Distance"
]

print(f"🏁 PRODUCTION START. RAM: {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MB")

# --- 1. Load Graph ---
print("1. Loading High-Fidelity Graph...")
G = ox.load_graphml(GRAPH_FILE) 
target_crs = G.graph['crs']
print(f"   Graph Ready. Nodes: {len(G.nodes):,}, Edges: {len(G.edges):,}")

# --- 2. Generate Data (Targeted Routes) ---
print(f"2. Generating {TOTAL_TRIPS} Targeted Routes (5 Average + 5 Edge Cases)...")
np.random.seed(42)

# Reference hospital location (North Vancouver area - similar to image)
hospital_lat, hospital_lon = 49.32, -123.07

# Generate 5 "average" distance routes (20-60km range)
# These simulate typical nurse home visits in the Lower Mainland
avg_routes = []
distances = [15, 30, 45, 60, 75]  # Target distances in km (approximated)
for i, target_km in enumerate(distances[:5]):
    # Calculate approximate degree offset for target distance
    # ~111 km per degree latitude, ~85 km per degree longitude at this latitude
    offset_deg = target_km / APPROX_KM_PER_DEGREE
    angle = np.random.uniform(0, 2 * np.pi)
    dest_lat = hospital_lat + offset_deg * np.cos(angle)
    dest_lon = hospital_lon + offset_deg * np.sin(angle)
    avg_routes.append((hospital_lon, hospital_lat, dest_lon, dest_lat))

# Generate 5 "edge case" routes
# 1. Very short (5km) - local urban route
edge_routes = [
    (hospital_lon, hospital_lat, hospital_lon - 0.04, hospital_lat + 0.03),  # ~5km north
    # 2. Long distance (100km+) - to Abbotsford area (like the image shows)
    (hospital_lon, hospital_lat, -122.3, 49.05),  # ~80km east to Abbotsford
    # 3. Cross-region (50km) - Vancouver to Surrey
    (-123.1, 49.28, -122.85, 49.10),
    # 4. Coastal route - Richmond to North Vancouver via bridges
    (-123.13, 49.17, -123.07, 49.32),
    # 5. Extreme distance - North Van to eastern suburbs
    (-123.07, 49.32, -122.5, 49.15)
]

# Combine all routes
all_routes = avg_routes + edge_routes
orig_x = [r[0] for r in all_routes]
orig_y = [r[1] for r in all_routes]
dest_x = [r[2] for r in all_routes]
dest_y = [r[3] for r in all_routes]

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
all_routes = [None] * TOTAL_TRIPS  # Store all routes for auditing

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
                all_routes[idx] = r_list[i]  # Store the route
        
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
def audit_route(G_graph, route, route_id, route_type, distance_km, time_min):
    """Audit a single route and show detailed segment information"""
    print(f"\n{'='*100}")
    print(f"🕵️ ROUTE {route_id} AUDIT ({route_type})")
    print(f"   Distance: {distance_km:.2f} km | Travel Time: {time_min:.2f} min | Avg Speed: {(distance_km/(time_min/60)):.1f} km/h")
    print(f"{'='*100}")
    
    segments = list(zip(route[:-1], route[1:]))
    
    # Collect segment data
    segment_data = []
    for u, v in segments:
        edges = G_graph[u][v]
        best_key = min(edges, key=lambda k: edges[k].get('travel_time', float('inf')))
        data = edges[best_key]
        
        segment_data.append({
            'class': str(data.get('ROADCLASS', 'Unknown')),
            'trafficdir': str(data.get('TRAFFICDIR', 'Unknown')),
            'surface': str(data.get('PAVSURF', 'Unknown')),
            'speed': float(data.get('speed_kph', 0)),
            'length': float(data.get('length', 0)),
            'time': float(data.get('travel_time', 0))
        })
    
    # Print header
    print(f"\n   {'SEG':<4} | {'CLASS':<18} | {'TRAFFICDIR':<18} | {'SURFACE':<12} | {'SPEED':<8} | {'DIST (m)':<10} | {'TIME (min)':<10}")
    print("   " + "-" * 105)
    
    # Show first 10, middle 5, and last 10 segments
    total_segs = len(segment_data)
    if total_segs <= 25:
        # Show all if 25 or fewer
        indices_to_show = list(range(total_segs))
    else:
        # Show first 10, middle 5, last 10
        indices_to_show = (list(range(10)) + 
                          list(range(total_segs//2 - 2, total_segs//2 + 3)) + 
                          list(range(total_segs - 10, total_segs)))
    
    shown = set()
    for i, seg in enumerate(segment_data):
        if i in indices_to_show:
            shown.add(i)
            print(f"   {i+1:<4} | {seg['class'][:18]:<18} | {seg['trafficdir'][:18]:<18} | "
                  f"{seg['surface'][:12]:<12} | {seg['speed']:<8.1f} | {seg['length']:<10.1f} | {seg['time']:<10.2f}")
        elif i == 10 and total_segs > 25:
            print(f"   ... ({total_segs - 25} intermediate segments omitted) ...")
    
    # Print summary statistics
    print(f"\n   {'--- ROUTE SUMMARY ---':<100}")
    
    # Road class distribution
    class_counts = {}
    total_dist_by_class = {}
    for seg in segment_data:
        rc = seg['class']
        class_counts[rc] = class_counts.get(rc, 0) + 1
        total_dist_by_class[rc] = total_dist_by_class.get(rc, 0) + seg['length']
    
    print(f"   Road Class Distribution:")
    for rc in sorted(class_counts.keys()):
        count = class_counts[rc]
        dist = total_dist_by_class[rc] / 1000
        pct = (dist / distance_km) * 100
        print(f"     {rc:<18}: {count:>3} segments, {dist:>6.2f} km ({pct:>5.1f}%)")
    
    # Surface distribution
    surface_counts = {}
    for seg in segment_data:
        surf = seg['surface']
        surface_counts[surf] = surface_counts.get(surf, 0) + 1
    
    print(f"\n   Surface Distribution:")
    for surf in sorted(surface_counts.keys()):
        count = surface_counts[surf]
        pct = (count / total_segs) * 100
        print(f"     {surf:<18}: {count:>3} segments ({pct:>5.1f}%)")
    
    return segment_data


# --- 8. AUDIT ALL ROUTES ---
print(f"\n{'#'*100}")
print(f"# DETAILED ROUTE AUDITS")
print(f"{'#'*100}")

# Store route info for final summary
route_info = []

for trip_id in range(TOTAL_TRIPS):
    if all_routes[trip_id] is not None:
        route = all_routes[trip_id]
        dist = all_distances[trip_id]
        time_val = all_times[trip_id]
        
        # Determine route type
        if trip_id < 5:
            route_type = f"Average Distance Route (Target: ~{[15,30,45,60,75][trip_id]}km)"
        else:
            route_type = f"Edge Case: {EDGE_CASE_LABELS[trip_id - 5]}"
        
        segment_data = audit_route(G, route, trip_id + 1, route_type, dist, time_val)
        route_info.append({
            'id': trip_id + 1,
            'type': route_type,
            'distance': dist,
            'time': time_val,
            'segments': len(segment_data)
        })

# --- 9. FINAL SUMMARY ---
print(f"\n{'#'*100}")
print(f"# FINAL SUMMARY - ALL ROUTES")
print(f"{'#'*100}\n")

print(f"{'ID':<4} | {'TYPE':<50} | {'DIST (km)':<10} | {'TIME (min)':<11} | {'SEGMENTS':<8}")
print("-" * 100)
for info in route_info:
    print(f"{info['id']:<4} | {info['type']:<50} | {info['distance']:<10.2f} | {info['time']:<11.2f} | {info['segments']:<8}")

print("\n" + "="*100)
print("✅ SIMULATION COMPLETE")
print("="*100)