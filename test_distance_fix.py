#!/usr/bin/env python3
"""
Test script to validate the edge geometry projection fix.

This test verifies that:
1. Edge geometries are properly projected to meters
2. Distance calculations use projected coordinates
3. Routes produce reasonable distance values
4. Reverse edges have correct geometry
"""

import osmnx as ox
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, LineString
import numpy as np


def test_edge_geometry_projection():
    """Test that edge geometries are properly projected"""
    
    print("=" * 70)
    print("Testing Edge Geometry Projection")
    print("=" * 70)
    
    # Create a test graph with BC coordinates (Vancouver area)
    # Distance between these points should be ~729 meters
    nodes = gpd.GeoDataFrame({
        'osmid': [1, 2],
        'geometry': [Point(-123.1, 49.2), Point(-123.09, 49.2)],
        'x': [-123.1, -123.09],
        'y': [49.2, 49.2]
    }, crs='EPSG:4326').set_index('osmid')
    
    edges = gpd.GeoDataFrame({
        'u': [1],
        'v': [2],
        'key': [0],
        'geometry': [LineString([(-123.1, 49.2), (-123.09, 49.2)])],
        'ROADCLASS': ['Local'],
        'PAVSURF': ['Paved'],
        'TRAFFICDIR': ['Both Directions'],
        'safe_speed': [40]
    }, crs='EPSG:4326').set_index(['u', 'v', 'key'])
    
    # Create and project graph
    G = ox.graph_from_gdfs(nodes, edges)
    orig_length = G[1][2][0]['geometry'].length
    
    print(f"\n1. Original edge geometry length: {orig_length:.6f} degrees")
    assert orig_length < 0.02, "Original length should be in degrees (small value)"
    
    # Project graph (mimics factory_analysis.py)
    G_proj = ox.project_graph(G)
    
    # Without the fix, geometry is still in degrees
    unfixed_length = G_proj[1][2][0]['geometry'].length
    print(f"2. After ox.project_graph (unfixed): {unfixed_length:.6f} degrees")
    
    # Apply the fix: manually project geometries
    target_crs = G_proj.graph['crs']
    for u, v, k, data in G_proj.edges(keys=True, data=True):
        if 'geometry' in data:
            geom_gdf = gpd.GeoSeries([data['geometry']], crs='EPSG:4326')
            projected_geom = geom_gdf.to_crs(target_crs)[0]
            data['geometry'] = projected_geom
    
    fixed_length = G_proj[1][2][0]['geometry'].length
    print(f"3. After manual projection (fixed): {fixed_length:.2f} meters")
    
    # Verify the fix
    assert fixed_length > 700 and fixed_length < 750, \
        f"Fixed length should be ~729 meters, got {fixed_length:.2f}"
    
    print("  ✅ PASS - Geometry correctly projected to meters")
    
    return G_proj


def test_reverse_edge_geometry(G_proj):
    """Test that reverse edges have properly reversed geometry"""
    
    print("\n" + "=" * 70)
    print("Testing Reverse Edge Geometry")
    print("=" * 70)
    
    # Get forward edge data
    forward_data = G_proj[1][2][0]
    forward_length = forward_data['geometry'].length
    forward_coords = list(forward_data['geometry'].coords)
    
    print(f"\n1. Forward edge length: {forward_length:.2f} meters")
    print(f"   Forward coords: start={forward_coords[0]}, end={forward_coords[-1]}")
    
    # Create reverse edge with reversed geometry (mimics factory_analysis.py)
    reverse_data = forward_data.copy()
    if 'geometry' in reverse_data:
        coords = list(reverse_data['geometry'].coords)
        reverse_data['geometry'] = LineString(coords[::-1])
    
    reverse_length = reverse_data['geometry'].length
    reverse_coords = list(reverse_data['geometry'].coords)
    
    print(f"2. Reverse edge length: {reverse_length:.2f} meters")
    print(f"   Reverse coords: start={reverse_coords[0]}, end={reverse_coords[-1]}")
    
    # Verify
    assert abs(forward_length - reverse_length) < 0.01, \
        "Forward and reverse edges should have same length"
    
    assert reverse_coords[0] == forward_coords[-1], \
        "Reverse edge should start where forward edge ends"
    
    assert reverse_coords[-1] == forward_coords[0], \
        "Reverse edge should end where forward edge starts"
    
    print("  ✅ PASS - Reverse edge geometry correctly reversed")


def test_distance_calculation():
    """Test that route distance calculations are reasonable"""
    
    print("\n" + "=" * 70)
    print("Testing Route Distance Calculation")
    print("=" * 70)
    
    # Create a multi-segment route
    nodes = gpd.GeoDataFrame({
        'osmid': [1, 2, 3, 4],
        'geometry': [
            Point(-123.1, 49.2),
            Point(-123.09, 49.2),   # ~729m east
            Point(-123.08, 49.2),   # ~729m east
            Point(-123.07, 49.2)    # ~729m east
        ],
        'x': [-123.1, -123.09, -123.08, -123.07],
        'y': [49.2, 49.2, 49.2, 49.2]
    }, crs='EPSG:4326').set_index('osmid')
    
    edges = gpd.GeoDataFrame({
        'u': [1, 2, 3],
        'v': [2, 3, 4],
        'key': [0, 0, 0],
        'geometry': [
            LineString([(-123.1, 49.2), (-123.09, 49.2)]),
            LineString([(-123.09, 49.2), (-123.08, 49.2)]),
            LineString([(-123.08, 49.2), (-123.07, 49.2)])
        ],
        'safe_speed': [40, 60, 110]
    }, crs='EPSG:4326').set_index(['u', 'v', 'key'])
    
    # Create and project graph
    G = ox.graph_from_gdfs(nodes, edges)
    G_proj = ox.project_graph(G)
    
    # Apply geometry projection fix
    target_crs = G_proj.graph['crs']
    for u, v, k, data in G_proj.edges(keys=True, data=True):
        if 'geometry' in data:
            geom_gdf = gpd.GeoSeries([data['geometry']], crs='EPSG:4326')
            projected_geom = geom_gdf.to_crs(target_crs)[0]
            data['geometry'] = projected_geom
    
    # Calculate physics (mimics factory_analysis.py)
    for u, v, k, data in G_proj.edges(keys=True, data=True):
        length = data['geometry'].length if 'geometry' in data else 0
        speed = float(data.get('safe_speed', 50))
        time_min = ((length / 1000) / speed) * 60
        
        data['length'] = round(length, 2)
        data['travel_time'] = round(time_min, 3)
        data['speed_kph'] = round(speed, 1)
    
    # Calculate route distance (mimics production_simulation.py)
    route = [1, 2, 3, 4]
    total_distance = 0.0
    total_time = 0.0
    
    print("\nRoute segments:")
    for i, (u, v) in enumerate(zip(route[:-1], route[1:])):
        edges = G_proj[u][v]
        best_key = min(edges, key=lambda k: edges[k].get('travel_time', float('inf')))
        edge_data = edges[best_key]
        
        length = float(edge_data.get('length', 0))
        time = float(edge_data.get('travel_time', 0))
        speed = float(edge_data.get('speed_kph', 0))
        
        total_distance += length
        total_time += time
        
        print(f"  Segment {i+1}: {length:.2f}m @ {speed:.0f} km/h = {time:.2f} min")
    
    total_distance_km = total_distance / 1000
    print(f"\nTotal route distance: {total_distance_km:.2f} km")
    print(f"Total travel time: {total_time:.2f} minutes")
    
    # Verify reasonable values
    # 3 segments of ~729m each = ~2.19 km total
    assert total_distance_km > 2.0 and total_distance_km < 2.5, \
        f"Total distance should be ~2.19 km, got {total_distance_km:.2f}"
    
    assert total_time > 0 and total_time < 10, \
        f"Total time should be reasonable (< 10 min), got {total_time:.2f}"
    
    print("  ✅ PASS - Route calculations produce reasonable values")


def test_large_scale_simulation():
    """Test that simulated route doesn't produce absurd distances"""
    
    print("\n" + "=" * 70)
    print("Testing Large-Scale Route Simulation")
    print("=" * 70)
    
    # Simulate a typical urban route with many segments
    # Vancouver to Burnaby: about 10 km
    np.random.seed(42)
    
    num_segments = 50
    lons = np.linspace(-123.1, -123.0, num_segments + 1)  # ~10 km
    lats = np.full(num_segments + 1, 49.2)
    
    node_ids = list(range(num_segments + 1))
    nodes = gpd.GeoDataFrame({
        'osmid': node_ids,
        'geometry': [Point(lon, lat) for lon, lat in zip(lons, lats)],
        'x': lons,
        'y': lats
    }, crs='EPSG:4326').set_index('osmid')
    
    edge_list = []
    for i in range(num_segments):
        edge_list.append({
            'u': i,
            'v': i + 1,
            'key': 0,
            'geometry': LineString([(lons[i], lats[i]), (lons[i+1], lats[i+1])]),
            'ROADCLASS': 'Arterial' if i % 5 == 0 else 'Local',
            'safe_speed': 60 if i % 5 == 0 else 40
        })
    
    edges = gpd.GeoDataFrame(edge_list, crs='EPSG:4326').set_index(['u', 'v', 'key'])
    
    # Create and project graph
    G = ox.graph_from_gdfs(nodes, edges)
    G_proj = ox.project_graph(G)
    
    # Apply fix
    target_crs = G_proj.graph['crs']
    for u, v, k, data in G_proj.edges(keys=True, data=True):
        if 'geometry' in data:
            geom_gdf = gpd.GeoSeries([data['geometry']], crs='EPSG:4326')
            projected_geom = geom_gdf.to_crs(target_crs)[0]
            data['geometry'] = projected_geom
            data['length'] = projected_geom.length
    
    # Calculate total distance
    route = node_ids
    total_distance = 0.0
    
    for u, v in zip(route[:-1], route[1:]):
        edge_data = G_proj[u][v][0]
        total_distance += float(edge_data.get('length', 0))
    
    total_distance_km = total_distance / 1000
    
    print(f"\nSimulated route:")
    print(f"  Segments: {num_segments}")
    print(f"  Total distance: {total_distance_km:.2f} km")
    
    # Verify it's reasonable (should be ~7-8 km based on actual projection, not 200,000 km!)
    assert total_distance_km > 5 and total_distance_km < 15, \
        f"Distance should be ~7-8 km, got {total_distance_km:.2f}"
    
    assert total_distance_km < 1000, \
        f"Distance should NOT be absurd (like 208,097 km), got {total_distance_km:.2f}"
    
    print(f"  ✅ PASS - Large route produces reasonable distance ({total_distance_km:.2f} km)")


def main():
    print("\n" + "=" * 70)
    print("BC Routing Engine - Distance Calculation Fix Validation")
    print("=" * 70)
    
    try:
        G_proj = test_edge_geometry_projection()
        test_reverse_edge_geometry(G_proj)
        test_distance_calculation()
        test_large_scale_simulation()
        
        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
        print("\nThe edge geometry projection fix resolves the distance issues:")
        print("1. ✅ Edge geometries are now properly projected to meters")
        print("2. ✅ Reverse edges have correctly reversed geometries")
        print("3. ✅ Distance calculations use projected coordinates")
        print("4. ✅ Routes produce reasonable distances (not 208,097 km!)")
        print("\nKey fix:")
        print("  After ox.project_graph(G), manually project all edge geometries")
        print("  from EPSG:4326 (degrees) to the target CRS (meters).")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
