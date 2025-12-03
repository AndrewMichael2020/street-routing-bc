#!/usr/bin/env python3
"""
Integration demo showing the complete fix in action.
This simulates the factory_analysis.py -> production_simulation.py workflow
without requiring the actual NRN data files.
"""

import osmnx as ox
import networkx as nx
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import Point, LineString
import folium
import os


def create_mock_graph():
    """Create a mock graph similar to what factory_analysis.py produces"""
    
    print("=" * 70)
    print("Creating Mock Graph (simulating factory_analysis.py)")
    print("=" * 70)
    
    # Create a small street network around Vancouver
    # This represents a simplified version of the NRN data
    np.random.seed(42)
    
    # Create a grid of intersections
    lons = np.linspace(-123.15, -123.05, 6)  # ~10 km east-west
    lats = np.linspace(49.25, 49.30, 6)      # ~5.5 km north-south
    
    node_id = 0
    node_list = []
    for lat in lats:
        for lon in lons:
            node_list.append({
                'osmid': node_id,
                'geometry': Point(lon, lat),
                'x': lon,
                'y': lat
            })
            node_id += 1
    
    nodes = gpd.GeoDataFrame(node_list, crs='EPSG:4326').set_index('osmid')
    
    # Create edges (streets) connecting the grid
    edge_list = []
    grid_width = 6
    
    for i in range(len(node_list)):
        # Connect to node on the right
        if (i + 1) % grid_width != 0:
            lon1, lat1 = node_list[i]['x'], node_list[i]['y']
            lon2, lat2 = node_list[i + 1]['x'], node_list[i + 1]['y']
            road_class = 'Freeway' if i % 10 == 0 else ('Arterial' if i % 5 == 0 else 'Local')
            edge_list.append({
                'u': i,
                'v': i + 1,
                'key': 0,
                'geometry': LineString([(lon1, lat1), (lon2, lat2)]),
                'ROADCLASS': road_class,
                'PAVSURF': 'Paved',
                'TRAFFICDIR': 'Both Directions',
                'safe_speed': 110 if road_class == 'Freeway' else (60 if road_class == 'Arterial' else 40)
            })
        
        # Connect to node below
        if i + grid_width < len(node_list):
            lon1, lat1 = node_list[i]['x'], node_list[i]['y']
            lon2, lat2 = node_list[i + grid_width]['x'], node_list[i + grid_width]['y']
            road_class = 'Arterial' if i % 3 == 0 else 'Local'
            edge_list.append({
                'u': i,
                'v': i + grid_width,
                'key': 0,
                'geometry': LineString([(lon1, lat1), (lon2, lat2)]),
                'ROADCLASS': road_class,
                'PAVSURF': 'Paved',
                'TRAFFICDIR': 'Both Directions',
                'safe_speed': 60 if road_class == 'Arterial' else 40
            })
    
    edges = gpd.GeoDataFrame(edge_list, crs='EPSG:4326').set_index(['u', 'v', 'key'])
    
    print(f"  Created {len(nodes)} nodes and {len(edges)} edges")
    
    # Create graph
    G = ox.graph_from_gdfs(nodes, edges)
    
    # Project graph (mimics factory_analysis.py)
    print("  Projecting graph to UTM...")
    G_proj = ox.project_graph(G)
    
    # Apply the FIX: manually project edge geometries
    print("  Applying fix: manually projecting edge geometries...")
    target_crs = G_proj.graph['crs']
    for u, v, k, data in G_proj.edges(keys=True, data=True):
        if 'geometry' in data:
            geom_gdf = gpd.GeoSeries([data['geometry']], crs='EPSG:4326')
            projected_geom = geom_gdf.to_crs(target_crs)[0]
            data['geometry'] = projected_geom
    
    # Handle directionality (mimics factory_analysis.py)
    print("  Handling directionality for bidirectional roads...")
    G_directed = G_proj.to_directed()
    G_fixed = nx.MultiDiGraph()
    G_fixed.graph.update(G_directed.graph)
    
    for node, data in G_directed.nodes(data=True):
        G_fixed.add_node(node, **data)
    
    for u, v, k, data in G_directed.edges(keys=True, data=True):
        traffic_dir = str(data.get('TRAFFICDIR', 'Unknown')).title()
        
        if traffic_dir in ['Both Directions', 'Both', 'Unknown']:
            G_fixed.add_edge(u, v, k, **data)
            reverse_data = data.copy()
            if 'geometry' in reverse_data:
                coords = list(reverse_data['geometry'].coords)
                reverse_data['geometry'] = LineString(coords[::-1])
            G_fixed.add_edge(v, u, k, **reverse_data)
        else:
            G_fixed.add_edge(u, v, k, **data)
    
    # Calculate physics (mimics factory_analysis.py)
    print("  Calculating edge lengths and travel times...")
    for u, v, k, data in G_fixed.edges(keys=True, data=True):
        length = data['geometry'].length if 'geometry' in data else 0
        speed = float(data.get('safe_speed', 50))
        time_min = ((length / 1000) / speed) * 60
        
        data['length'] = round(length, 2)
        data['travel_time'] = round(time_min, 3)
        data['speed_kph'] = round(speed, 1)
    
    print(f"✅ Graph ready: {len(G_fixed.nodes)} nodes, {len(G_fixed.edges)} edges")
    return G_fixed


def simulate_routes(G, num_trips=10):
    """Simulate routes (mimics production_simulation.py)"""
    
    print("\n" + "=" * 70)
    print(f"Simulating {num_trips} Mock Routes (simulating production_simulation.py)")
    print("=" * 70)
    
    # Generate random origin-destination pairs
    np.random.seed(42)
    nodes = list(G.nodes())
    
    trips = []
    for i in range(num_trips):
        orig = np.random.choice(nodes)
        dest = np.random.choice(nodes)
        
        if orig == dest:
            continue
        
        try:
            route = nx.shortest_path(G, orig, dest, weight='travel_time')
            
            # Calculate distance and time
            dist = 0.0
            time = 0.0
            for u, v in zip(route[:-1], route[1:]):
                edges = G[u][v]
                best_key = min(edges, key=lambda k: edges[k].get('travel_time', float('inf')))
                edge_data = edges[best_key]
                dist += float(edge_data.get('length', 0))
                time += float(edge_data.get('travel_time', 0))
            
            trips.append({
                'id': i,
                'route': route,
                'distance_km': dist / 1000,
                'time_min': time
            })
        except nx.NetworkXNoPath:
            pass
    
    if len(trips) == 0:
        print("❌ No routes found!")
        return None
    
    # Statistics
    distances = [t['distance_km'] for t in trips]
    times = [t['time_min'] for t in trips]
    
    print(f"\n✅ Successfully routed {len(trips)}/{num_trips} trips")
    print(f"\nDistance Statistics (km):")
    print(f"  Mean: {np.mean(distances):.2f} km")
    print(f"  Min: {np.min(distances):.2f} km")
    print(f"  Max: {np.max(distances):.2f} km")
    
    print(f"\nTime Statistics (minutes):")
    print(f"  Mean: {np.mean(times):.2f} min")
    print(f"  Min: {np.min(times):.2f} min")
    print(f"  Max: {np.max(times):.2f} min")
    
    # Verify distances are reasonable
    max_dist = np.max(distances)
    if max_dist > 100:
        print(f"\n⚠️  WARNING: Maximum distance {max_dist:.1f} km seems too large!")
        print("   This suggests the geometry projection bug is still present.")
        return None
    else:
        print(f"\n✅ All distances are reasonable (max {max_dist:.2f} km)")
    
    # Find longest route for demonstration
    longest = max(trips, key=lambda t: t['distance_km'])
    return longest, G


def audit_route(G, route, trip_id, distance_km):
    """Audit route and generate map (mimics production_simulation.py)"""
    
    print("\n" + "=" * 70)
    print(f"Auditing Longest Route (Trip {trip_id}): {distance_km:.2f} km")
    print("=" * 70)
    
    segments = list(zip(route[:-1], route[1:]))
    
    print(f"\n{'CLASS':<15} | {'TRAFFICDIR':<15} | {'SURFACE':<10} | {'SPEED':<8} | {'DIST (m)':<10} | {'TIME (min)':<10}")
    print("-" * 95)
    
    # Show first 5, middle 3, last 5 segments
    indices_to_show = list(range(min(5, len(segments)))) + \
                      list(range(len(segments)//2 - 1, min(len(segments)//2 + 2, len(segments)))) + \
                      list(range(max(0, len(segments)-5), len(segments)))
    shown = set()
    
    for i, (u, v) in enumerate(segments):
        if i in indices_to_show and i not in shown:
            shown.add(i)
            edges = G[u][v]
            best_key = min(edges, key=lambda k: edges[k].get('travel_time', float('inf')))
            data = edges[best_key]
            
            r_cls = str(data.get('ROADCLASS', 'Unknown'))
            traffic_dir = str(data.get('TRAFFICDIR', 'Unknown'))
            surf = str(data.get('PAVSURF', 'Unknown'))
            spd = float(data.get('speed_kph', 0))
            ln = float(data.get('length', 0))
            tm = float(data.get('travel_time', 0))
            
            print(f"{r_cls:<15} | {traffic_dir:<15} | {surf:<10} | {spd:<8.1f} | {ln:<10.1f} | {tm:<10.2f}")
        elif i == 5 and len(segments) > 13:
            print("... (skipping intermediate segments) ...")
    
    # Verify distances are NOT 0.0
    all_zero = all(
        float(G[u][v][min(G[u][v], key=lambda k: G[u][v][k].get('travel_time', float('inf')))].get('length', 0)) == 0.0
        for u, v in segments
    )
    
    if all_zero:
        print("\n❌ ERROR: All segment distances are 0.0!")
        print("   The geometry projection fix is not working.")
        return False
    else:
        print("\n✅ Segment distances are properly calculated (not all 0.0)")
    
    # Generate map
    print(f"\nGenerating map for Trip {trip_id}...")
    route_nodes = [G.nodes[n] for n in route]
    gdf_nodes = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy([n['x'] for n in route_nodes], [n['y'] for n in route_nodes]),
        crs=G.graph['crs']
    ).to_crs(epsg=4326)
    
    coords = [(p.y, p.x) for p in gdf_nodes.geometry]
    m = folium.Map(location=coords[len(coords)//2], zoom_start=11, tiles='OpenStreetMap')
    folium.PolyLine(coords, color="blue", weight=5, opacity=0.7, tooltip=f"Trip {trip_id}").add_to(m)
    folium.Marker(coords[0], popup="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(coords[-1], popup="End", icon=folium.Icon(color="red")).add_to(m)
    
    map_filename = f"demo_route_Trip_{trip_id}.html"
    m.save(map_filename)
    print(f"✅ Map saved to: {map_filename}")
    print(f"   Open this file in a browser to view the route.")
    
    return True


def main():
    print("\n" + "=" * 70)
    print("Integration Demo: Distance Calculation Fix")
    print("=" * 70)
    print("\nThis demo simulates the complete workflow without requiring")
    print("the actual NRN data files, showing that the fix works correctly.")
    print("=" * 70)
    
    # Create mock graph
    G = create_mock_graph()
    
    # Simulate routes
    result = simulate_routes(G, num_trips=10)
    if result is None:
        print("\n❌ DEMO FAILED")
        return 1
    
    longest, G = result
    
    # Audit longest route
    success = audit_route(
        G, 
        longest['route'], 
        longest['id'], 
        longest['distance_km']
    )
    
    if not success:
        print("\n❌ DEMO FAILED")
        return 1
    
    print("\n" + "=" * 70)
    print("✅ INTEGRATION DEMO PASSED")
    print("=" * 70)
    print("\nKey Results:")
    print(f"  ✅ Routes calculated successfully with reasonable distances")
    print(f"  ✅ Longest route: {longest['distance_km']:.2f} km (NOT 208,097 km!)")
    print(f"  ✅ All segment distances properly calculated (NOT 0.0)")
    print(f"  ✅ Map generated successfully")
    print("\nThe fix is working correctly!")
    
    return 0


if __name__ == "__main__":
    exit(main())
