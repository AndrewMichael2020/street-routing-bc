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
TOTAL_TRIPS = 10        # Number of mock trips to simulate (reduced for faster testing)
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
    print(f"   {'CLASS':<15} | {'TRAFFICDIR':<15} | {'SURFACE':<10} | {'SPEED':<8} | {'DIST (m)':<10} | {'TIME (min)':<10}")
    print("   " + "-" * 95)
    
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
            traffic_dir = str(data.get('TRAFFICDIR', 'Unknown'))
            surf = str(data.get('PAVSURF', 'Unknown'))
            spd = float(data.get('speed_kph', 0))
            ln = float(data.get('length', 0))
            tm = float(data.get('travel_time', 0))
            
            print(f"   {r_cls[:15]:<15} | {traffic_dir[:15]:<15} | {surf[:10]:<10} | {spd:<8.1f} | {ln:<10.1f} | {tm:<10.2f}")
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
    
    # Save map to HTML file
    map_filename = f"route_map_{title.replace(' ', '_')}.html"
    m.save(map_filename)
    print(f"   Map saved to: {map_filename}")
    
    # Try to open in browser (cross-platform compatible)
    try:
        map_path = Path(map_filename).absolute().as_uri()
        webbrowser.open(map_path)
        print(f"   Opening map in browser...")
    except Exception as e:
        print(f"   Could not open browser: {e}")
        print(f"   Please open {map_filename} manually to view the map.")

if longest_route_data['route']:
    long_id = longest_route_data['id']
    dist = longest_route_data['dist']
    print(f"\n🏆 Longest Urban Route (ID {long_id}): {dist:.1f} km")
    audit_and_plot(G, longest_route_data['route'], title=f"Trip {long_id}")
else:
    print("\nNo routes found to plot.")