#!/usr/bin/env python3
"""
NRN Data Loader Module
Handles fetching and merging of NRN data from multiple sources:
1. Main road network (GPKG file)
2. Alleyways (MapServer Layer 91)
3. Additional metadata fields (route numbers, names, etc.)
"""

import requests
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString


class NRNDataLoader:
    """
    Loads and merges National Road Network (NRN) data from multiple sources.
    """
    
    # API endpoints
    ALLEYWAYS_API = "https://geo.statcan.gc.ca/geo_wa/rest/services/NRN-RRN/nrn_rrn/MapServer/91/query"
    
    # Default parameters
    DEFAULT_ALLEY_SPEED = 15  # km/h - typical alleyway speed
    
    def __init__(self):
        self.gdf_roads = None
        self.gdf_alleys = None
        
    def load_main_roads(self, gpkg_filename, layer_name, columns=None):
        """
        Load main road network from GPKG file.
        
        Args:
            gpkg_filename: Path to GPKG file
            layer_name: Layer name to load
            columns: List of columns to keep (None for all)
        
        Returns:
            GeoDataFrame with road data
        """
        print("📂 Loading main road network from GPKG...")
        
        if columns:
            gdf = gpd.read_file(gpkg_filename, layer=layer_name)
            existing_cols = [c for c in columns if c in gdf.columns]
            gdf = gdf[existing_cols]
        else:
            gdf = gpd.read_file(gpkg_filename, layer=layer_name)
        
        print(f"   ✅ Loaded {len(gdf):,} road segments")
        print(f"   📍 CRS: {gdf.crs}")
        
        self.gdf_roads = gdf
        return gdf
    
    def fetch_alleyways(self, timeout=60, max_retries=3):
        """
        Fetch alleyways data from NRN MapServer API (Layer 91).
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        
        Returns:
            GeoDataFrame with alleyways data, or None if fetch fails
        """
        print("\n🌐 Fetching alleyways from NRN MapServer API...")
        print(f"   URL: {self.ALLEYWAYS_API}")
        
        params = {
            'where': '1=1',
            'outFields': '*',
            'returnGeometry': 'true',
            'f': 'geojson'
        }
        
        for attempt in range(max_retries):
            try:
                print(f"   Attempt {attempt + 1}/{max_retries}...")
                response = requests.get(self.ALLEYWAYS_API, params=params, timeout=timeout)
                response.raise_for_status()
                
                geojson_data = response.json()
                
                if geojson_data.get('features'):
                    gdf = gpd.GeoDataFrame.from_features(geojson_data['features'])
                    gdf.set_crs('EPSG:4617', inplace=True)  # NAD83(CSRS)
                    
                    print(f"   ✅ Successfully fetched {len(gdf):,} alleyway segments")
                    print(f"   📍 CRS: {gdf.crs}")
                    
                    self.gdf_alleys = gdf
                    return gdf
                else:
                    print("   ⚠️  No features found in response")
                    return None
                    
            except requests.exceptions.RequestException as e:
                print(f"   ⚠️  Attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    print(f"   ❌ All {max_retries} attempts failed")
                    return None
            except Exception as e:
                print(f"   ❌ Error processing response: {e}")
                return None
        
        return None
    
    def harmonize_alleyways_schema(self, gdf_alleys):
        """
        Harmonize alleyways schema to match main road network.
        
        Args:
            gdf_alleys: GeoDataFrame with alleyways data
        
        Returns:
            GeoDataFrame with harmonized schema
        """
        print("\n🔧 Harmonizing alleyways schema...")
        
        # Create a copy to avoid modifying original
        gdf = gdf_alleys.copy()
        
        # Map alleyways fields to main road network fields
        field_mapping = {
            'roadclass': 'ROADCLASS',
            'l_stname_c': 'L_STNAME_C',
            'r_stname_c': 'R_STNAME_C',
            'rtename1en': 'RTENAME1EN',
            'rtename2en': 'RTENAME2EN',
            'rtename3en': 'RTENAME3EN',
            'rtename4en': 'RTENAME4EN',
            'rtnumber1': 'RTNUMBER1',
            'rtnumber2': 'RTNUMBER2',
            'rtnumber3': 'RTNUMBER3',
            'rtnumber4': 'RTNUMBER4',
            'rtnumber5': 'RTNUMBER5',
            'l_placenam': 'L_PLACENAM',
            'r_placenam': 'R_PLACENAM',
            'datasetnam': 'DATASETNAM'
        }
        
        # Rename columns that exist
        existing_mappings = {old: new for old, new in field_mapping.items() if old in gdf.columns}
        if existing_mappings:
            gdf.rename(columns=existing_mappings, inplace=True)
            print(f"   ✅ Renamed {len(existing_mappings)} columns")
        
        # Add missing columns with default values
        required_cols = ['ROADCLASS', 'PAVSURF', 'PAVSTATUS', 'TRAFFICDIR', 'SPEED', 'ROADJURIS', 'NID', 'ROADSEGID']
        
        for col in required_cols:
            if col not in gdf.columns:
                if col == 'ROADCLASS':
                    gdf[col] = 'Alleyway'  # Tag as alleyway
                elif col == 'PAVSURF':
                    gdf[col] = 'Paved'  # Assume paved
                elif col == 'PAVSTATUS':
                    gdf[col] = 'Paved'
                elif col == 'TRAFFICDIR':
                    gdf[col] = 'Both Directions'  # Alleys are typically bidirectional
                elif col == 'SPEED':
                    gdf[col] = self.DEFAULT_ALLEY_SPEED  # 15 km/h
                elif col == 'ROADJURIS':
                    gdf[col] = 'Municipal'
                elif col == 'NID':
                    # Generate unique IDs for alleyways (prefix with 'ALLEY_')
                    gdf[col] = [f'ALLEY_{i}' for i in range(len(gdf))]
                elif col == 'ROADSEGID':
                    # Generate unique segment IDs
                    gdf[col] = [f'ALLEYSEG_{i}' for i in range(len(gdf))]
                else:
                    gdf[col] = 'Unknown'
        
        print(f"   ✅ Schema harmonized - added {len([c for c in required_cols if c not in gdf_alleys.columns])} missing columns")
        
        return gdf
    
    def merge_datasets(self, gdf_roads, gdf_alleys):
        """
        Merge main roads and alleyways into a single dataset.
        
        Args:
            gdf_roads: Main road network GeoDataFrame
            gdf_alleys: Alleyways GeoDataFrame (already harmonized)
        
        Returns:
            Merged GeoDataFrame
        """
        print("\n🔀 Merging road network and alleyways...")
        
        # Ensure both have the same CRS
        if gdf_alleys.crs != gdf_roads.crs:
            print(f"   Reprojecting alleyways from {gdf_alleys.crs} to {gdf_roads.crs}")
            gdf_alleys = gdf_alleys.to_crs(gdf_roads.crs)
        
        # Find common columns
        common_cols = list(set(gdf_roads.columns) & set(gdf_alleys.columns))
        
        # Keep only common columns for consistency
        gdf_roads_subset = gdf_roads[common_cols]
        gdf_alleys_subset = gdf_alleys[common_cols]
        
        # Concatenate
        gdf_merged = pd.concat([gdf_roads_subset, gdf_alleys_subset], ignore_index=True)
        
        print(f"   ✅ Merged datasets:")
        print(f"      Main roads: {len(gdf_roads):,} segments")
        print(f"      Alleyways:  {len(gdf_alleys):,} segments")
        print(f"      Total:      {len(gdf_merged):,} segments")
        
        return gdf_merged
    
    def extract_metadata(self, gdf):
        """
        Extract additional metadata fields for enhanced routing.
        
        Args:
            gdf: GeoDataFrame with road data
        
        Returns:
            GeoDataFrame with enhanced metadata
        """
        print("\n📋 Extracting additional metadata...")
        
        metadata_added = []
        
        # 1. Route Numbers (RTNUMBER1-5)
        route_cols = ['RTNUMBER1', 'RTNUMBER2', 'RTNUMBER3', 'RTNUMBER4', 'RTNUMBER5']
        route_cols_exist = [col for col in route_cols if col in gdf.columns]
        
        if route_cols_exist:
            # Combine route numbers into a single field
            gdf['ROUTE_NUMBERS'] = gdf[route_cols_exist].apply(
                lambda row: ','.join([str(v) for v in row if v and str(v).lower() not in ['none', 'nan', '']]), 
                axis=1
            )
            gdf['ROUTE_NUMBERS'] = gdf['ROUTE_NUMBERS'].replace('', 'None')
            
            routes_with_numbers = (gdf['ROUTE_NUMBERS'] != 'None').sum()
            print(f"   ✅ Route numbers: {routes_with_numbers:,}/{len(gdf):,} segments ({routes_with_numbers/len(gdf)*100:.1f}%)")
            metadata_added.append('ROUTE_NUMBERS')
        
        # 2. Route Names (RTENAME1-4EN)
        name_cols = ['RTENAME1EN', 'RTENAME2EN', 'RTENAME3EN', 'RTENAME4EN']
        name_cols_exist = [col for col in name_cols if col in gdf.columns]
        
        if name_cols_exist:
            gdf['ROUTE_NAMES'] = gdf[name_cols_exist].apply(
                lambda row: ','.join([str(v) for v in row if v and str(v).lower() not in ['none', 'nan', '']]),
                axis=1
            )
            gdf['ROUTE_NAMES'] = gdf['ROUTE_NAMES'].replace('', 'None')
            
            routes_with_names = (gdf['ROUTE_NAMES'] != 'None').sum()
            print(f"   ✅ Route names: {routes_with_names:,}/{len(gdf):,} segments ({routes_with_names/len(gdf)*100:.1f}%)")
            metadata_added.append('ROUTE_NAMES')
        
        # 3. Street Names (L_STNAME_C, R_STNAME_C)
        if 'L_STNAME_C' in gdf.columns or 'R_STNAME_C' in gdf.columns:
            # Use left street name, fall back to right if left is missing
            gdf['STREET_NAME'] = gdf.get('L_STNAME_C', gdf.get('R_STNAME_C', 'Unnamed'))
            
            named_streets = (gdf['STREET_NAME'].notna() & (gdf['STREET_NAME'] != 'None')).sum()
            print(f"   ✅ Street names: {named_streets:,}/{len(gdf):,} segments ({named_streets/len(gdf)*100:.1f}%)")
            metadata_added.append('STREET_NAME')
        
        # 4. Place Names (L_PLACENAM, R_PLACENAM)
        if 'L_PLACENAM' in gdf.columns or 'R_PLACENAM' in gdf.columns:
            gdf['PLACE_NAME'] = gdf.get('L_PLACENAM', gdf.get('R_PLACENAM', 'Unknown'))
            
            named_places = (gdf['PLACE_NAME'].notna() & (gdf['PLACE_NAME'] != 'None')).sum()
            print(f"   ✅ Place names: {named_places:,}/{len(gdf):,} segments ({named_places/len(gdf)*100:.1f}%)")
            metadata_added.append('PLACE_NAME')
        
        print(f"   📊 Total metadata fields added: {len(metadata_added)}")
        
        return gdf
    
    def load_and_merge_all(self, gpkg_filename, layer_name, columns=None, 
                          include_alleyways=True, include_metadata=True):
        """
        Complete data loading pipeline: load main roads, fetch alleyways, merge, and extract metadata.
        
        Args:
            gpkg_filename: Path to GPKG file
            layer_name: Layer name to load
            columns: List of columns to keep from main roads
            include_alleyways: Whether to fetch and merge alleyways
            include_metadata: Whether to extract additional metadata
        
        Returns:
            GeoDataFrame with complete road network
        """
        print("="*80)
        print("NRN DATA LOADER - COMPLETE PIPELINE")
        print("="*80)
        
        # 1. Load main roads
        gdf_roads = self.load_main_roads(gpkg_filename, layer_name, columns)
        
        # 2. Fetch alleyways (if enabled)
        if include_alleyways:
            gdf_alleys = self.fetch_alleyways()
            
            if gdf_alleys is not None and len(gdf_alleys) > 0:
                # Harmonize schema
                gdf_alleys_harmonized = self.harmonize_alleyways_schema(gdf_alleys)
                
                # Merge with main roads
                gdf_merged = self.merge_datasets(gdf_roads, gdf_alleys_harmonized)
            else:
                print("   ⚠️  Alleyways fetch failed - continuing with main roads only")
                gdf_merged = gdf_roads
        else:
            print("\n⏭️  Skipping alleyways (disabled)")
            gdf_merged = gdf_roads
        
        # 3. Extract metadata (if enabled)
        if include_metadata:
            gdf_merged = self.extract_metadata(gdf_merged)
        else:
            print("\n⏭️  Skipping metadata extraction (disabled)")
        
        print("\n" + "="*80)
        print("✅ DATA LOADING COMPLETE")
        print(f"   Total segments: {len(gdf_merged):,}")
        print(f"   CRS: {gdf_merged.crs}")
        print("="*80 + "\n")
        
        return gdf_merged


if __name__ == "__main__":
    # Example usage
    print("NRN Data Loader - Example Usage\n")
    
    loader = NRNDataLoader()
    
    # Example: Load main roads only (without alleyways)
    print("Example 1: Load main roads only (no alleyways, no extra metadata)")
    print("-" * 80)
    
    # This would be used in factory_analysis.py like:
    # gdf_roads = loader.load_and_merge_all(
    #     gpkg_filename="NRN_BC_14_0_GPKG_en.gpkg",
    #     layer_name="NRN_BC_14_0_ROADSEG",
    #     columns=['geometry', 'SPEED', 'ROADCLASS', 'PAVSURF', 'PAVSTATUS', 'ROADJURIS', 'TRAFFICDIR', 'NID', 'ROADSEGID'],
    #     include_alleyways=True,  # Enable alleyways
    #     include_metadata=True    # Enable metadata extraction
    # )
    
    print("\n✅ Module ready for integration with factory_analysis.py")
