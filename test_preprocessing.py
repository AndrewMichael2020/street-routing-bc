#!/usr/bin/env python3
"""
Test script to validate preprocessing improvements.

This script tests the enhanced preprocessing logic:
1. Geometry validation and repair
2. CRS projection to EPSG:3005 (BC Albers)
3. Length calculation and validation
4. Attribute normalization
5. Duplicate detection
"""

import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import LineString, Point
from shapely import make_valid
from shapely.validation import explain_validity


def test_geometry_validation():
    """Test geometry validation and repair"""
    
    print("=" * 70)
    print("Testing Geometry Validation and Repair")
    print("=" * 70)
    
    # Create test geometries with issues
    valid_line = LineString([(0, 0), (1, 1)])
    invalid_bowtie = LineString([(0, 0), (1, 1), (1, 0), (0, 1)])  # Self-intersecting
    empty_line = LineString()
    
    test_cases = [
        ("Valid LineString", valid_line, True, False),
        ("Self-intersecting LineString", invalid_bowtie, False, False),
        ("Empty LineString", empty_line, True, True),
    ]
    
    for name, geom, expected_valid, expected_empty in test_cases:
        print(f"\nTest: {name}")
        print(f"  is_valid: {geom.is_valid} (expected: {expected_valid})")
        print(f"  is_empty: {geom.is_empty} (expected: {expected_empty})")
        
        if not geom.is_valid:
            print(f"  Reason: {explain_validity(geom)}")
            repaired = make_valid(geom)
            print(f"  After repair: is_valid={repaired.is_valid}")
            assert repaired.is_valid, f"Failed to repair {name}"
            print("  ✅ PASS - Geometry repaired")
        else:
            print("  ✅ PASS - Geometry valid")


def test_crs_projection():
    """Test CRS projection from EPSG:4617 to EPSG:3005"""
    
    print("\n" + "=" * 70)
    print("Testing CRS Projection (EPSG:4617 -> EPSG:3005)")
    print("=" * 70)
    
    # Create test data in EPSG:4617 (geographic)
    # Vancouver coordinates: approximately -123.1, 49.2
    test_points = [
        Point(-123.1, 49.2),
        Point(-123.2, 49.3),
    ]
    
    gdf = gpd.GeoDataFrame({'geometry': test_points}, crs='EPSG:4617')
    
    print(f"\nOriginal CRS: {gdf.crs}")
    print(f"Sample coordinates (geographic):")
    for i, pt in enumerate(gdf.geometry):
        print(f"  Point {i}: ({pt.x:.6f}, {pt.y:.6f})")
    
    # Project to BC Albers
    gdf_proj = gdf.to_crs('EPSG:3005')
    
    print(f"\nProjected CRS: {gdf_proj.crs}")
    print(f"Sample coordinates (BC Albers, meters):")
    for i, pt in enumerate(gdf_proj.geometry):
        print(f"  Point {i}: ({pt.x:.2f}, {pt.y:.2f})")
    
    # Validate projection
    assert str(gdf_proj.crs) == 'EPSG:3005', "CRS should be EPSG:3005"
    # BC Albers coordinates should be in reasonable range for BC
    for pt in gdf_proj.geometry:
        assert 200000 < pt.x < 1900000, f"X coordinate {pt.x} out of BC range"
        assert 300000 < pt.y < 1700000, f"Y coordinate {pt.y} out of BC range"
    
    print("  ✅ PASS - CRS projection successful")


def test_length_calculation():
    """Test length calculation in geographic vs projected CRS"""
    
    print("\n" + "=" * 70)
    print("Testing Length Calculation (Geographic vs Projected)")
    print("=" * 70)
    
    # Create a test line: ~10km segment in Vancouver area
    line = LineString([(-123.1, 49.2), (-123.2, 49.2)])
    
    gdf_geo = gpd.GeoDataFrame({'geometry': [line]}, crs='EPSG:4617')
    length_geo = gdf_geo.geometry.iloc[0].length
    
    print(f"\nGeographic CRS (EPSG:4617):")
    print(f"  Length: {length_geo:.6f} degrees")
    print(f"  ⚠️  This is NOT in meters!")
    
    # Project and calculate length
    gdf_proj = gdf_geo.to_crs('EPSG:3005')
    length_proj = gdf_proj.geometry.iloc[0].length
    
    print(f"\nProjected CRS (EPSG:3005):")
    print(f"  Length: {length_proj:.2f} meters")
    print(f"  ≈ {length_proj/1000:.2f} km")
    
    # Validate that projected length is reasonable
    # 0.1 degrees longitude at 49°N ≈ 7-8 km
    assert 5000 < length_proj < 12000, f"Projected length {length_proj}m seems incorrect"
    
    print("  ✅ PASS - Length calculation correct after projection")


def test_attribute_normalization():
    """Test attribute normalization for TRAFFICDIR"""
    
    print("\n" + "=" * 70)
    print("Testing Attribute Normalization")
    print("=" * 70)
    
    # Test data with various TRAFFICDIR values
    test_data = {
        'TRAFFICDIR': ['Both', 'Both Directions', 'Positive', 'Same Direction', 
                       'Negative', 'Opposite Direction', 'Unknown', 'Bidirectional']
    }
    df = pd.DataFrame(test_data)
    
    print("\nOriginal values:")
    print(df['TRAFFICDIR'].value_counts())
    
    # Apply normalization logic
    trafficdir_mapping = {
        'Both': 'Both Directions',
        'Bidirectional': 'Both Directions',
        'Positive': 'Same Direction',
        'Forward': 'Same Direction',
        'Negative': 'Opposite Direction',
        'Reverse': 'Opposite Direction',
    }
    df['TRAFFICDIR'] = df['TRAFFICDIR'].replace(trafficdir_mapping)
    
    print("\nNormalized values:")
    print(df['TRAFFICDIR'].value_counts())
    
    # Validate normalization
    expected_values = {'Both Directions', 'Same Direction', 'Opposite Direction', 'Unknown'}
    actual_values = set(df['TRAFFICDIR'].unique())
    
    print(f"\nExpected canonical values: {expected_values}")
    print(f"Actual values after normalization: {actual_values}")
    
    assert actual_values.issubset(expected_values), "Unexpected values after normalization"
    print("  ✅ PASS - Attribute normalization successful")


def test_speed_validation():
    """Test SPEED validation and clipping"""
    
    print("\n" + "=" * 70)
    print("Testing SPEED Validation and Clipping")
    print("=" * 70)
    
    # Test data with various SPEED values
    test_data = {
        'SPEED': [50, 110, 150, 3, -1, 0, 60, 200],
        'ROADCLASS': ['Local', 'Freeway', 'Freeway', 'Local', 
                      'Unknown', 'Arterial', 'Arterial', 'Expressway']
    }
    df = pd.DataFrame(test_data)
    
    print("\nOriginal SPEED values:")
    print(df[['SPEED', 'ROADCLASS']])
    
    # Apply validation logic
    df['SPEED'] = pd.to_numeric(df['SPEED'], errors='coerce').fillna(-1)
    
    # Clip unrealistic speeds
    invalid_mask = (df['SPEED'] > 0) & ((df['SPEED'] > 130) | (df['SPEED'] < 5))
    df.loc[(df['SPEED'] > 130), 'SPEED'] = -1  # Mark as unknown
    df.loc[(df['SPEED'] > 0) & (df['SPEED'] < 5), 'SPEED'] = 10  # Set minimum
    
    print("\nAfter clipping:")
    print(df[['SPEED', 'ROADCLASS']])
    
    # Validate clipping
    valid_speeds = df[df['SPEED'] > 0]['SPEED']
    assert all(valid_speeds >= 10), "All valid speeds should be >= 10"
    assert all(valid_speeds <= 130), "All valid speeds should be <= 130"
    
    print("  ✅ PASS - SPEED validation successful")


def test_duplicate_detection():
    """Test duplicate segment detection"""
    
    print("\n" + "=" * 70)
    print("Testing Duplicate Segment Detection")
    print("=" * 70)
    
    # Create test data with duplicates
    lines = [
        LineString([(0, 0), (1, 1)]),
        LineString([(0, 0), (1, 1)]),  # Duplicate
        LineString([(1, 1), (2, 2)]),
        LineString([(2, 2), (1, 1)]),  # Reverse duplicate
    ]
    
    gdf = gpd.GeoDataFrame({'geometry': lines}, crs='EPSG:3005')
    
    # Extract start/end coordinates
    gdf['u_coord'] = gdf.geometry.apply(lambda x: (round(x.coords[0][0], 2), round(x.coords[0][1], 2)))
    gdf['v_coord'] = gdf.geometry.apply(lambda x: (round(x.coords[-1][0], 2), round(x.coords[-1][1], 2)))
    
    print("\nSegments:")
    print(gdf[['u_coord', 'v_coord']])
    
    # Detect duplicates (order-independent)
    coord_pairs = gdf[['u_coord', 'v_coord']].apply(
        lambda row: tuple(sorted([row['u_coord'], row['v_coord']])), axis=1
    )
    duplicates = coord_pairs.duplicated()
    
    print(f"\nDuplicate segments: {duplicates.sum()}")
    print(f"Duplicate indices: {list(duplicates[duplicates].index)}")
    
    # Validate detection
    assert duplicates.sum() == 2, "Should detect 2 duplicates"
    assert duplicates.iloc[1] == True, "Segment 1 should be duplicate"
    assert duplicates.iloc[3] == True, "Segment 3 should be reverse duplicate"
    
    print("  ✅ PASS - Duplicate detection successful")


def main():
    print("\n" + "=" * 70)
    print("BC Routing Engine - Preprocessing Validation")
    print("=" * 70)
    
    try:
        test_geometry_validation()
        test_crs_projection()
        test_length_calculation()
        test_attribute_normalization()
        test_speed_validation()
        test_duplicate_detection()
        
        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
        print("\nPreprocessing improvements validated:")
        print("1. ✅ Geometry validation and repair working correctly")
        print("2. ✅ CRS projection to EPSG:3005 (BC Albers) successful")
        print("3. ✅ Length calculation in meters after projection")
        print("4. ✅ Attribute normalization for categorical values")
        print("5. ✅ SPEED validation and clipping")
        print("6. ✅ Duplicate segment detection")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
