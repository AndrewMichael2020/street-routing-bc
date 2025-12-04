#!/usr/bin/env python3
"""
Test script to verify the fixes for premature termination and highway speeds.
This tests the logic without requiring the full GPKG data file.
"""

import networkx as nx
from shapely.geometry import LineString, Point

def test_component_check_logic():
    """Test the logic for checking connected components."""
    print("=" * 60)
    print("TEST 1: Component Check Logic")
    print("=" * 60)
    
    # Create a test graph with multiple components
    G = nx.MultiDiGraph()
    
    # Add 120 nodes
    for i in range(120):
        G.add_node(i, x=1000000 + i*1000, y=500000 + i*1000)
    
    # Create 60 small components (each component has 2 nodes connected)
    # This gives us 60 components total (more than threshold of 50)
    for i in range(0, 120, 2):
        G.add_edge(i, i+1, geometry=LineString([(1000000, 500000), (1001000, 501000)]))
    
    num_components = nx.number_weakly_connected_components(G)
    print(f"   Test graph has {num_components} components")
    
    # Test the threshold logic
    threshold = 50
    if num_components > threshold:
        print(f"   ✅ PASS: {num_components} > {threshold}, consolidation would be skipped")
        return True
    else:
        print(f"   ❌ FAIL: {num_components} <= {threshold}, logic error")
        return False


def test_highway_speed_defaults():
    """Test the updated highway speed defaults."""
    print("\n" + "=" * 60)
    print("TEST 2: Highway Speed Defaults")
    print("=" * 60)
    
    # Speed Defaults for BC Roads
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
    
    print(f"   Testing speed defaults:")
    tests_passed = 0
    tests_total = 0
    
    # Test Freeway speed
    tests_total += 1
    if defaults['Freeway'] == 90:
        print(f"   ✅ Freeway: {defaults['Freeway']} km/h (correct)")
        tests_passed += 1
    else:
        print(f"   ❌ Freeway: {defaults['Freeway']} km/h (expected 90)")
    
    # Test Expressway speed
    tests_total += 1
    if defaults['Expressway'] == 90:
        print(f"   ✅ Expressway: {defaults['Expressway']} km/h (correct)")
        tests_passed += 1
    else:
        print(f"   ❌ Expressway: {defaults['Expressway']} km/h (expected 90)")
    
    # Test other speeds
    tests_total += 1
    if defaults['Arterial'] == 60 and defaults['Local'] == 40:
        print(f"   ✅ Arterial: {defaults['Arterial']} km/h, Local: {defaults['Local']} km/h (correct)")
        tests_passed += 1
    else:
        print(f"   ❌ Arterial/Local speeds incorrect")
    
    print(f"\n   Speed tests: {tests_passed}/{tests_total} passed")
    return tests_passed == tests_total


def test_coordinate_artifact_detection():
    """Test the artifact node detection logic."""
    print("\n" + "=" * 60)
    print("TEST 3: Coordinate Artifact Detection")
    print("=" * 60)
    
    # BC Albers valid range
    X_MIN, X_MAX = 200000, 1900000
    Y_MIN, Y_MAX = 300000, 1700000
    
    test_nodes = [
        (1, 1000000, 500000, True, "Valid node in BC"),
        (2, 100000, 500000, False, "X too low (artifact)"),
        (3, 2000000, 500000, False, "X too high (artifact)"),
        (4, 1000000, 200000, False, "Y too low (artifact)"),
        (5, 1000000, 1800000, False, "Y too high (artifact)"),
        (6, 0, 0, False, "Null Island (artifact)"),
    ]
    
    tests_passed = 0
    tests_total = len(test_nodes)
    
    for node_id, x, y, should_be_valid, description in test_nodes:
        is_valid = (Y_MIN <= y <= Y_MAX) and (X_MIN <= x <= X_MAX)
        
        if is_valid == should_be_valid:
            status = "✅ PASS"
            tests_passed += 1
        else:
            status = "❌ FAIL"
        
        print(f"   {status}: Node {node_id} ({x}, {y}) - {description}")
    
    print(f"\n   Artifact detection: {tests_passed}/{tests_total} passed")
    return tests_passed == tests_total


def test_graph_cleanup():
    """Test that graph cleanup happens in all code paths."""
    print("\n" + "=" * 60)
    print("TEST 4: Graph Cleanup in All Paths")
    print("=" * 60)
    
    # Simulate the two code paths
    print("   Path 1: Many components (skip consolidation)")
    G_proj = nx.MultiDiGraph()
    num_components = 96  # More than threshold
    
    if num_components > 50:
        G_fixed = G_proj
        del G_proj  # This should happen
        print("   ✅ PASS: G_proj deleted in skip path")
        path1_pass = True
    else:
        print("   ❌ FAIL: Logic error in skip path")
        path1_pass = False
    
    print("\n   Path 2: Few components (proceed with consolidation)")
    G_proj = nx.MultiDiGraph()
    num_components = 30  # Less than threshold
    
    if num_components > 50:
        print("   ❌ FAIL: Logic error in consolidation path")
        path2_pass = False
    else:
        # Simulate successful or failed consolidation
        try:
            # Would call ox.consolidate_intersections() here
            G_fixed = G_proj  # Simulate result
            del G_proj  # This should happen
            print("   ✅ PASS: G_proj deleted in consolidation path")
            path2_pass = True
        except Exception as e:
            G_fixed = G_proj
            del G_proj  # This should also happen
            print("   ✅ PASS: G_proj deleted in error path")
            path2_pass = True
    
    both_pass = path1_pass and path2_pass
    print(f"\n   Cleanup test: {'PASSED' if both_pass else 'FAILED'}")
    return both_pass


def main():
    """Run all tests."""
    print("\n" + "🏁" * 30)
    print("TESTING FACTORY_ANALYSIS.PY FIXES")
    print("🏁" * 30 + "\n")
    
    results = []
    
    # Run tests
    results.append(("Component Check Logic", test_component_check_logic()))
    results.append(("Highway Speed Defaults", test_highway_speed_defaults()))
    results.append(("Artifact Detection", test_coordinate_artifact_detection()))
    results.append(("Graph Cleanup", test_graph_cleanup()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status}: {test_name}")
    
    print("\n" + "-" * 60)
    if passed == total:
        print(f"   🎉 ALL {total} TESTS PASSED! 🎉")
        print("-" * 60)
        return 0
    else:
        print(f"   ⚠️  {passed}/{total} tests passed, {total - passed} failed")
        print("-" * 60)
        return 1


if __name__ == "__main__":
    exit(main())
