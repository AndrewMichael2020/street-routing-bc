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
    
    # API endpoints for different NRN layers
    BASE_API = "https://geo.statcan.gc.ca/geo_wa/rest/services/NRN-RRN/nrn_rrn/MapServer"
    
    # Layer IDs from MapServer
    LAYERS = {
        'blocked_passage': 2,     # Blocked passage / Passage obstrué
        'trans_canada': 35,       # Trans-Canada Highway / Route Transcanadienne
        'national_highway': 49,   # National Highway System / Réseau routier national
        'major_roads': 63,        # Major roads / Routes principales
        'local_roads': 77,        # Local roads / Routes locales
        'alleyways': 91           # Alleyways / Ruelles
    }
    
    # Default parameters
    DEFAULT_ALLEY_SPEED = 15  # km/h - typical alleyway speed
    SPATIAL_JOIN_BUFFER_M = 5  # meters - buffer for spatial joins to handle slight misalignments
    BLOCKED_PASSAGE_BUFFER_M = 20  # meters - buffer for blocked passage points
    
    def __init__(self):
        self.gdf_roads = None
        self.gdf_alleys = None
        self.metadata_layers = {}  # Store metadata from various layers
    
    @staticmethod
    def _filter_non_empty_values(row, exclude_values=None):
        """
        Helper function to filter out empty/invalid values from a row.
        
        Args:
            row: Pandas Series (row of DataFrame)
            exclude_values: List of values to exclude (default: ['none', 'nan', ''])
        
        Returns:
            List of valid values
        """
        if exclude_values is None:
            exclude_values = ['none', 'nan', '']
        
        return [str(v) for v in row if v and str(v).lower() not in exclude_values]
        
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
    
    def fetch_layer_data(self, layer_id, layer_name, timeout=60, max_retries=3):
        """
        Fetch data from a specific NRN MapServer layer.
        
        Args:
            layer_id: MapServer layer ID
            layer_name: Human-readable layer name (for logging)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        
        Returns:
            GeoDataFrame with layer data, or None if fetch fails
        """
        api_url = f"{self.BASE_API}/{layer_id}/query"
        info_url = f"{self.BASE_API}/{layer_id}?f=json"

        print(f"\n🌐 Fetching {layer_name} from NRN MapServer...")
        print(f"   URL: {api_url} (Layer {layer_id})")
        # 1) Ask the layer for its maxRecordCount (fallback to 1000 if missing)
        try:
            info_resp = requests.get(info_url, timeout=timeout)
            info_resp.raise_for_status()
            layer_info = info_resp.json()
            max_rec = int(layer_info.get('maxRecordCount', 1000))
            print(f"   Layer maxRecordCount: {max_rec}")
        except Exception:
            max_rec = 1000
            print(f"   Could not read layer info; using chunk size {max_rec}")

        params_base = {
            'where': '1=1',
            'outFields': '*',
            'returnGeometry': 'true',
            'f': 'geojson'
        }

        all_features = []
        offset = 0

        while True:
            params = params_base.copy()
            params.update({
                'resultOffset': offset,
                'resultRecordCount': max_rec
            })

            success = False
            feats = []
            for attempt in range(max_retries):
                try:
                    if attempt == 0:
                        print(f"   Fetching offset={offset}, count={max_rec}...", end='', flush=True)
                    else:
                        print(f" retry {attempt+1}/{max_retries}...", end='', flush=True)
                    resp = requests.get(api_url, params=params, timeout=timeout)
                    resp.raise_for_status()
                    data = resp.json()
                    feats = data.get('features') or []
                    all_features.extend(feats)
                    success = True
                    print(f" ✓")
                    break
                except requests.exceptions.RequestException as e:
                    if attempt < max_retries - 1:
                        print(f" ✗ ({e})", end='', flush=True)
                    else:
                        print(f" ✗ ({e}) - giving up")
                        raise

            if not success:
                break

            received = len(feats)
            print(f"   → Received {received:,} features (total: {len(all_features):,})")
            # Stop paging when:
            # - received == 0: No more data available (empty page)
            # - received < max_rec: Partial page received (last page)
            # Continue when received == max_rec: Full page suggests more data may exist
            if received == 0 or received < max_rec:
                break
            offset += received

        if not all_features:
            print("   ⚠️  No features found")
            return None

        gdf = gpd.GeoDataFrame.from_features(all_features)
        # layer CRS: try to set if `crs` present in layer_info or leave as default
        gdf.set_crs('EPSG:4617', inplace=True)  # NAD83(CSRS) as before
        print(f"   ✅ Successfully fetched {len(gdf):,} features")
        print(f"   📍 CRS: {gdf.crs}")
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
        gdf = self.fetch_layer_data(
            layer_id=self.LAYERS['alleyways'],
            layer_name='Alleyways',
            timeout=timeout,
            max_retries=max_retries
        )
        
        if gdf is not None:
            self.gdf_alleys = gdf
        
        return gdf
    
    def fetch_metadata_layers(self, layers=None, timeout=60, max_retries=3):
        """
        Fetch additional metadata layers (Trans-Canada, National Highway, etc.).
        
        Args:
            layers: List of layer names to fetch (None for all available)
                   Options: 'blocked_passage', 'trans_canada', 'national_highway', 
                           'major_roads', 'local_roads'
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        
        Returns:
            Dictionary mapping layer names to GeoDataFrames
        """
        if layers is None:
            # Fetch all metadata layers except alleyways (fetched separately)
            layers = ['blocked_passage', 'trans_canada', 'national_highway', 
                     'major_roads', 'local_roads']
        
        print("\n" + "="*80)
        print("FETCHING METADATA LAYERS")
        print("="*80)
        
        metadata = {}
        
        for layer_name in layers:
            if layer_name not in self.LAYERS:
                print(f"   ⚠️  Unknown layer: {layer_name} - skipping")
                continue
            
            layer_id = self.LAYERS[layer_name]
            
            # Format layer name for display
            display_name = layer_name.replace('_', ' ').title()
            
            gdf = self.fetch_layer_data(
                layer_id=layer_id,
                layer_name=display_name,
                timeout=timeout,
                max_retries=max_retries
            )
            
            if gdf is not None:
                metadata[layer_name] = gdf
                self.metadata_layers[layer_name] = gdf
        
        print("\n" + "="*80)
        print(f"✅ METADATA FETCH COMPLETE - {len(metadata)}/{len(layers)} layers loaded")
        print("="*80 + "\n")
        
        return metadata
    
    def harmonize_alleyways_schema(self, gdf_alleys):
        """
        Harmonize alleyways schema to match main road network.
        More robust: normalizes incoming column names, ensures types,
        generates stable prefixed IDs, and canonicalizes key fields.
        """
        print("\n🔧 Harmonizing alleyways schema...")
        if gdf_alleys is None:
            print("   ⚠️  No alleyways GeoDataFrame provided")
            return None

        # Work on a copy and preserve CRS
        gdf = gdf_alleys.copy()
        crs = gdf.crs

        # Normalize column names to lower-case for mapping robustness
        col_map_lower = {c.lower(): c for c in gdf.columns}
        gdf.columns = [c.lower() for c in gdf.columns]

        # Field mapping from lowercase source -> target uppercase names
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

        # Apply renames for columns that exist
        rename_map = {src: dst for src, dst in field_mapping.items() if src in gdf.columns}
        if rename_map:
            # rename lowers -> uppercase target names
            gdf = gdf.rename(columns=rename_map)

        # If geometry column name changed, ensure it's 'geometry'
        # (GeoPandas normally keeps 'geometry' but just in case)
        if 'geometry' not in gdf.columns and gdf.geometry.name != 'geometry':
            gdf.set_geometry(gdf.geometry.name or gdf.columns[-1], inplace=True)

        # Ensure we have a simple sequential index to base generated IDs on
        gdf = gdf.reset_index(drop=True)

        # Force ROADCLASS and canonical values
        gdf['ROADCLASS'] = 'Alleyway'

        # Required columns and defaults
        required_cols = {
            'PAVSURF': 'Paved',
            'PAVSTATUS': 'Paved',
            'TRAFFICDIR': 'Both Directions',
            'SPEED': self.DEFAULT_ALLEY_SPEED,
            'ROADJURIS': 'Municipal',
        }

        # Add / fill required cols
        for col, default in required_cols.items():
            if col not in gdf.columns:
                gdf[col] = default
            else:
                # if exists, fill missing values
                gdf[col] = gdf[col].fillna(default)

        # Generate stable, prefixed IDs if missing
        if 'NID' not in gdf.columns:
            gdf['NID'] = ['ALLEY_NID_{:08d}'.format(i) for i in range(len(gdf))]
        else:
            gdf['NID'] = gdf['NID'].fillna('').astype(str)
            missing_nid = gdf['NID'] == ''
            if missing_nid.any():
                gdf.loc[missing_nid, 'NID'] = ['ALLEY_NID_{:08d}'.format(i) for i in gdf[missing_nid].index]

        if 'ROADSEGID' not in gdf.columns:
            gdf['ROADSEGID'] = ['ALLEY_SEG_{:08d}'.format(i) for i in range(len(gdf))]
        else:
            gdf['ROADSEGID'] = gdf['ROADSEGID'].fillna('').astype(str)
            missing_rsid = gdf['ROADSEGID'] == ''
            if missing_rsid.any():
                gdf.loc[missing_rsid, 'ROADSEGID'] = ['ALLEY_SEG_{:08d}'.format(i) for i in gdf[missing_rsid].index]

        # Canonicalize TRAFFICDIR strings to main dataset vocabulary
        traffic_map = {
            'both': 'Both Directions',
            'bidirectional': 'Both Directions',
            'both directions': 'Both Directions',
            'positive': 'Same Direction',
            'forward': 'Same Direction',
            'same direction': 'Same Direction',
            'negative': 'Opposite Direction',
            'reverse': 'Opposite Direction',
            'opposite direction': 'Opposite Direction',
            '': 'Both Directions'
        }
        gdf['TRAFFICDIR'] = gdf['TRAFFICDIR'].astype(str).str.strip().str.lower().map(traffic_map).fillna('Both Directions')

        # Ensure SPEED is numeric (float) and fallback to default
        gdf['SPEED'] = pd.to_numeric(gdf['SPEED'], errors='coerce').fillna(self.DEFAULT_ALLEY_SPEED).astype(float)

        # Ensure PAVSURF / PAVSTATUS are strings with title case
        for c in ('PAVSURF', 'PAVSTATUS', 'ROADJURIS'):
            gdf[c] = gdf[c].astype(str).replace({'nan': 'Unknown', 'None': 'Unknown'}).str.title()

        # Restore CRS (keep original)
        gdf.set_crs(crs, inplace=True)

        print(f"   ✅ Schema harmonized - set ROADCLASS='Alleyway', added/fixed {', '.join(required_cols.keys())} and generated stable IDs")
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
    
    def enrich_with_metadata_layers(self, gdf_roads, metadata_layers):
        """
        Enrich main road network with metadata from additional layers.
        
        This adds flags like IS_TRANS_CANADA, IS_NATIONAL_HIGHWAY, etc.
        based on spatial joins with metadata layers.
        
        Args:
            gdf_roads: Main road network GeoDataFrame
            metadata_layers: Dictionary of metadata layer GeoDataFrames
        
        Returns:
            Enriched GeoDataFrame
        """
        print("\n🔗 Enriching road network with metadata layers...")
        
        gdf_enriched = gdf_roads.copy()
        
        # Ensure we're in a projected CRS for spatial operations (buffering requires meters)
        # If in geographic CRS (like EPSG:4617), reproject to BC Albers (EPSG:3005)
        target_crs = gdf_roads.crs
        use_projected = False
        projected_crs = 'EPSG:3005'  # BC Albers - metric
        
        if target_crs and target_crs.is_geographic:
            print(f"   ⚠️  Roads in geographic CRS ({target_crs}) - temporarily reprojecting to {projected_crs} for buffer operations")
            gdf_enriched = gdf_enriched.to_crs(projected_crs)
            use_projected = True
        
        # Track enrichment statistics
        enrichment_stats = {}
        
        # 1. Trans-Canada Highway flag
        if 'trans_canada' in metadata_layers:
            print("   Processing Trans-Canada Highway data...")
            gdf_tch = metadata_layers['trans_canada']
            if use_projected:
                gdf_tch = gdf_tch.to_crs(projected_crs)
            else:
                gdf_tch = gdf_tch.to_crs(target_crs)
            
            # Spatial join to find roads that are part of Trans-Canada
            # Use a small buffer to account for slight misalignments
            gdf_tch_buffered = gdf_tch.copy()
            gdf_tch_buffered['geometry'] = gdf_tch_buffered.geometry.buffer(self.SPATIAL_JOIN_BUFFER_M)
            
            joined = gpd.sjoin(gdf_enriched, gdf_tch_buffered, how='left', predicate='intersects')
            gdf_enriched['IS_TRANS_CANADA'] = joined.index_right.notna()
            
            tch_count = gdf_enriched['IS_TRANS_CANADA'].sum()
            enrichment_stats['Trans-Canada Highway'] = tch_count
            print(f"      ✅ Marked {tch_count:,} segments as Trans-Canada Highway")
        
        # 2. National Highway System flag
        if 'national_highway' in metadata_layers:
            print("   Processing National Highway System data...")
            gdf_nhs = metadata_layers['national_highway']
            if use_projected:
                gdf_nhs = gdf_nhs.to_crs(projected_crs)
            else:
                gdf_nhs = gdf_nhs.to_crs(target_crs)
            
            gdf_nhs_buffered = gdf_nhs.copy()
            gdf_nhs_buffered['geometry'] = gdf_nhs_buffered.geometry.buffer(self.SPATIAL_JOIN_BUFFER_M)
            
            joined = gpd.sjoin(gdf_enriched, gdf_nhs_buffered, how='left', predicate='intersects')
            gdf_enriched['IS_NATIONAL_HIGHWAY'] = joined.index_right.notna()
            
            nhs_count = gdf_enriched['IS_NATIONAL_HIGHWAY'].sum()
            enrichment_stats['National Highway System'] = nhs_count
            print(f"      ✅ Marked {nhs_count:,} segments as National Highway System")
        
        # 3. Major Roads designation
        if 'major_roads' in metadata_layers:
            print("   Processing Major Roads data...")
            gdf_major = metadata_layers['major_roads']
            if use_projected:
                gdf_major = gdf_major.to_crs(projected_crs)
            else:
                gdf_major = gdf_major.to_crs(target_crs)
            
            gdf_major_buffered = gdf_major.copy()
            gdf_major_buffered['geometry'] = gdf_major_buffered.geometry.buffer(self.SPATIAL_JOIN_BUFFER_M)
            
            joined = gpd.sjoin(gdf_enriched, gdf_major_buffered, how='left', predicate='intersects')
            gdf_enriched['IS_MAJOR_ROAD'] = joined.index_right.notna()
            
            major_count = gdf_enriched['IS_MAJOR_ROAD'].sum()
            enrichment_stats['Major Roads'] = major_count
            print(f"      ✅ Marked {major_count:,} segments as Major Roads")
        
        # 4. Blocked Passage points (mark segments as restricted)
        if 'blocked_passage' in metadata_layers:
            print("   Processing Blocked Passage data...")
            gdf_blocked = metadata_layers['blocked_passage']
            if use_projected:
                gdf_blocked = gdf_blocked.to_crs(projected_crs)
            else:
                gdf_blocked = gdf_blocked.to_crs(target_crs)
            
            # Buffer blocked passage points to find affected road segments
            gdf_blocked_buffered = gdf_blocked.copy()
            gdf_blocked_buffered['geometry'] = gdf_blocked_buffered.geometry.buffer(self.BLOCKED_PASSAGE_BUFFER_M)
            
            joined = gpd.sjoin(gdf_enriched, gdf_blocked_buffered, how='left', predicate='intersects')
            gdf_enriched['HAS_BLOCKED_PASSAGE'] = joined.index_right.notna()
            
            # Also store the blockage type if available
            if 'blkpassty' in gdf_blocked.columns:
                # Get the blockage type for segments with blocked passages
                blocked_types = joined.groupby(joined.index)['blkpassty'].first()
                gdf_enriched['BLOCKED_PASSAGE_TYPE'] = blocked_types
                gdf_enriched['BLOCKED_PASSAGE_TYPE'].fillna('None', inplace=True)
            
            blocked_count = gdf_enriched['HAS_BLOCKED_PASSAGE'].sum()
            enrichment_stats['Blocked Passages'] = blocked_count
            print(f"      ✅ Marked {blocked_count:,} segments with blocked passages")
        
        print(f"\n   📊 Enrichment Summary:")
        for category, count in enrichment_stats.items():
            print(f"      {category}: {count:,} segments")
        
        # Reproject back to original CRS if we temporarily reprojected
        if use_projected:
            print(f"   ✅ Reprojecting enriched data back to {target_crs}")
            gdf_enriched = gdf_enriched.to_crs(target_crs)
        
        return gdf_enriched
    
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
            # Combine route numbers into a single field using helper
            gdf['ROUTE_NUMBERS'] = gdf[route_cols_exist].apply(
                lambda row: ','.join(self._filter_non_empty_values(row)), 
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
            # Combine route names using helper
            gdf['ROUTE_NAMES'] = gdf[name_cols_exist].apply(
                lambda row: ','.join(self._filter_non_empty_values(row)),
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
                          include_alleyways=True, include_metadata=True,
                          include_metadata_layers=False, metadata_layer_list=None):
        """
        Complete data loading pipeline: load main roads, fetch alleyways, merge, and extract metadata.
        
        Args:
            gpkg_filename: Path to GPKG file
            layer_name: Layer name to load
            columns: List of columns to keep from main roads
            include_alleyways: Whether to fetch and merge alleyways
            include_metadata: Whether to extract additional metadata (route numbers, names)
            include_metadata_layers: Whether to fetch and enrich with MapServer metadata layers
            metadata_layer_list: List of metadata layers to fetch (None for all)
        
        Returns:
            GeoDataFrame with complete road network
        """
        print("="*80)
        print("NRN DATA LOADER - COMPLETE PIPELINE")
        print("="*80)
        
        # 1. Load main roads
        gdf_roads = self.load_main_roads(gpkg_filename, layer_name, columns)
        
        # 2. Fetch metadata layers (if enabled)
        metadata_layers = {}
        if include_metadata_layers:
            metadata_layers = self.fetch_metadata_layers(
                layers=metadata_layer_list,
                timeout=60,
                max_retries=3
            )
        
        # 3. Fetch alleyways (if enabled)
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
        
        # 4. Enrich with metadata layers (if enabled and available)
        if include_metadata_layers and metadata_layers:
            gdf_merged = self.enrich_with_metadata_layers(gdf_merged, metadata_layers)
        
        # 5. Extract metadata (if enabled)
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
