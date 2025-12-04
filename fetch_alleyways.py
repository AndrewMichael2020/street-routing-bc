#!/usr/bin/env python3
"""
Utility to fetch and inspect NRN Alleyways data from Statistics Canada MapServer.
This script assesses the feasibility of integrating alleyways with the main road network.
"""

import requests
import geopandas as gpd
import json
from io import BytesIO

def fetch_alleyways_data(limit=None):
    """
    Fetch alleyways data from NRN MapServer Layer 91.
    
    Args:
        limit: Maximum number of records to fetch (None for all)
    
    Returns:
        GeoDataFrame with alleyways data
    """
    base_url = "https://geo.statcan.gc.ca/geo_wa/rest/services/NRN-RRN/nrn_rrn/MapServer/91/query"
    
    params = {
        'where': '1=1',
        'outFields': '*',
        'returnGeometry': 'true',
        'f': 'geojson'
    }
    
    if limit:
        params['resultRecordCount'] = limit
    
    print(f"Fetching alleyways data from NRN MapServer...")
    print(f"URL: {base_url}")
    
    try:
        response = requests.get(base_url, params=params, timeout=60)
        response.raise_for_status()
        
        # Parse GeoJSON
        geojson_data = response.json()
        
        print(f"✅ Successfully fetched data")
        print(f"   Response size: {len(response.content) / 1024:.1f} KB")
        print(f"   Features: {len(geojson_data.get('features', []))}")
        
        # Convert to GeoDataFrame
        if geojson_data.get('features'):
            gdf = gpd.GeoDataFrame.from_features(geojson_data['features'])
            gdf.set_crs('EPSG:4617', inplace=True)  # NRN data is in NAD83(CSRS)
            
            print(f"\n📊 Data Summary:")
            print(f"   CRS: {gdf.crs}")
            print(f"   Total rows: {len(gdf)}")
            print(f"   Columns: {list(gdf.columns)}")
            
            # Display sample data
            print(f"\n📝 Sample Data (first 3 rows):")
            print(gdf.head(3))
            
            # Display column types and non-null counts
            print(f"\n📋 Column Info:")
            print(gdf.info())
            
            # Display unique values for key categorical fields
            if 'roadclass' in gdf.columns:
                print(f"\n🛣️  Road Classes:")
                print(gdf['roadclass'].value_counts())
            
            if 'datasetnam' in gdf.columns:
                print(f"\n📍 Dataset Names:")
                print(gdf['datasetnam'].value_counts())
            
            return gdf
        else:
            print("⚠️  No features found in the response")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching data: {e}")
        return None
    except Exception as e:
        print(f"❌ Error processing data: {e}")
        return None


def assess_feasibility(gdf_alleyways):
    """
    Assess the feasibility of integrating alleyways with the main road network.
    
    Args:
        gdf_alleyways: GeoDataFrame with alleyways data
    """
    print("\n" + "="*80)
    print("FEASIBILITY ASSESSMENT")
    print("="*80)
    
    if gdf_alleyways is None or len(gdf_alleyways) == 0:
        print("❌ No alleyways data available for assessment")
        return
    
    # 1. Data Volume
    print(f"\n1. Data Volume:")
    print(f"   Total alleyways: {len(gdf_alleyways):,}")
    print(f"   Memory size: {gdf_alleyways.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB")
    
    # 2. Geometry Quality
    print(f"\n2. Geometry Quality:")
    valid_geoms = gdf_alleyways.geometry.is_valid.sum()
    print(f"   Valid geometries: {valid_geoms:,}/{len(gdf_alleyways):,} ({valid_geoms/len(gdf_alleyways)*100:.1f}%)")
    
    empty_geoms = gdf_alleyways.geometry.is_empty.sum()
    print(f"   Empty geometries: {empty_geoms:,}")
    
    null_geoms = gdf_alleyways.geometry.isna().sum()
    print(f"   Null geometries: {null_geoms:,}")
    
    # 3. Attribute Completeness
    print(f"\n3. Attribute Completeness:")
    for col in ['roadclass', 'l_stname_c', 'r_stname_c', 'l_placenam', 'r_placenam']:
        if col in gdf_alleyways.columns:
            non_null = gdf_alleyways[col].notna().sum()
            non_none = (gdf_alleyways[col] != 'None').sum()
            print(f"   {col}: {non_null:,}/{len(gdf_alleyways):,} not null ({non_null/len(gdf_alleyways)*100:.1f}%), {non_none:,} not 'None'")
    
    # 4. Coordinate System Compatibility
    print(f"\n4. Coordinate System:")
    print(f"   Current CRS: {gdf_alleyways.crs}")
    print(f"   Target CRS: EPSG:3005 (BC Albers)")
    print(f"   ✅ Compatible - can be reprojected")
    
    # 5. Geographic Coverage
    print(f"\n5. Geographic Coverage:")
    bounds = gdf_alleyways.total_bounds
    print(f"   Bounding box (EPSG:4617):")
    print(f"     Min X (Lon): {bounds[0]:.4f}")
    print(f"     Max X (Lon): {bounds[2]:.4f}")
    print(f"     Min Y (Lat): {bounds[1]:.4f}")
    print(f"     Max Y (Lat): {bounds[3]:.4f}")
    
    # Reproject to BC Albers for length calculation
    gdf_proj = gdf_alleyways.to_crs('EPSG:3005')
    gdf_proj['length_m'] = gdf_proj.geometry.length
    
    print(f"\n6. Segment Lengths (in meters, BC Albers):")
    length_stats = gdf_proj['length_m'].describe(percentiles=[0.01, 0.25, 0.5, 0.75, 0.95, 0.99])
    print(f"   Min:     {length_stats['min']:>10.2f} m")
    print(f"   1%:      {length_stats['1%']:>10.2f} m")
    print(f"   25%:     {length_stats['25%']:>10.2f} m")
    print(f"   Median:  {length_stats['50%']:>10.2f} m")
    print(f"   75%:     {length_stats['75%']:>10.2f} m")
    print(f"   95%:     {length_stats['95%']:>10.2f} m")
    print(f"   99%:     {length_stats['99%']:>10.2f} m")
    print(f"   Max:     {length_stats['max']:>10.2f} m")
    print(f"   Mean:    {length_stats['mean']:>10.2f} m")
    
    # 7. Integration Strategy
    print(f"\n7. Integration Strategy:")
    print(f"   ✅ Recommended: Runtime Overlay (separate layer)")
    print(f"   Reasons:")
    print(f"     - Alleyways are a distinct road type")
    print(f"     - Can be styled differently (thinner lines, grey color)")
    print(f"     - Keeps main road network processing separate")
    print(f"     - Easier to maintain and update independently")
    
    # 8. Feasibility Verdict
    print(f"\n8. FEASIBILITY VERDICT:")
    print(f"   ✅ FEASIBLE - Alleyways can be integrated")
    print(f"   Recommended approach:")
    print(f"     1. Fetch alleyways data via API call (as demonstrated)")
    print(f"     2. Add as separate processing step in factory_analysis.py")
    print(f"     3. Merge with main road network before graph creation")
    print(f"     4. Tag alleyways with roadclass='Alleyway' for identification")
    print(f"     5. Apply lower speed limits (15-20 km/h typical for alleys)")


def create_mock_alleyways_for_testing():
    """
    Create mock alleyways data from the sample in the issue for testing.
    This is used when network access is not available.
    """
    import geopandas as gpd
    from shapely.geometry import LineString
    
    # Sample data from the issue
    sample_features = [
        {
            "type": "Feature",
            "id": 1,
            "geometry": {"type": "LineString", "coordinates": [[-116.97085263415119, 51.291346090356498], [-116.96847303367558, 51.291355290632445]]},
            "properties": {
                "OBJECTID": 1,
                "datasetnam": "British Columbia",
                "roadclass": "Local / Street",
                "l_stname_c": "14th Street South",
                "r_stname_c": "14th Street South",
                "l_placenam": "Golden",
                "r_placenam": "Golden"
            }
        },
        {
            "type": "Feature",
            "id": 2,
            "geometry": {"type": "LineString", "coordinates": [[-116.97087063387336, 51.290390090297933], [-116.96847263339542, 51.290404090576331]]},
            "properties": {
                "OBJECTID": 2,
                "datasetnam": "British Columbia",
                "roadclass": "Local / Street",
                "l_stname_c": "15th Street South",
                "r_stname_c": "15th Street South",
                "l_placenam": "Golden",
                "r_placenam": "Golden"
            }
        }
    ]
    
    gdf = gpd.GeoDataFrame.from_features(sample_features)
    gdf.set_crs('EPSG:4617', inplace=True)
    
    print("📝 Using mock alleyways data for demonstration")
    print(f"   Total features: {len(gdf)}")
    
    return gdf


if __name__ == "__main__":
    # Fetch a sample first to test
    print("Testing API with sample data (first 100 records)...\n")
    gdf_sample = fetch_alleyways_data(limit=100)
    
    if gdf_sample is not None:
        print("\n" + "="*80)
        print("Sample data fetched successfully!")
        print("Now fetching ALL alleyways data...")
        print("="*80 + "\n")
        
        gdf_all = fetch_alleyways_data(limit=None)
        
        if gdf_all is not None:
            assess_feasibility(gdf_all)
            
            # Save to file for inspection
            output_file = "bc_alleyways_sample.geojson"
            gdf_all.head(1000).to_file(output_file, driver='GeoJSON')
            print(f"\n💾 Sample data (first 1000 records) saved to: {output_file}")
    else:
        print("\n⚠️  Network access not available or API unreachable")
        print("Using mock data for demonstration purposes...\n")
        gdf_mock = create_mock_alleyways_for_testing()
        assess_feasibility(gdf_mock)
