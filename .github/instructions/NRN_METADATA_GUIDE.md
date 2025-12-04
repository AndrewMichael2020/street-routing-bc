# NRN Metadata Integration - Usage Guide

## Overview

This module extends the BC street routing engine with comprehensive metadata from Statistics Canada's National Road Network (NRN) MapServer. It provides:

1. **Alleyways Layer** - Complete alley/lane network for last-mile routing
2. **Trans-Canada Highway** - TCH designation for major routes
3. **National Highway System** - NHS classification for primary corridors
4. **Major Roads** - Principal arterial network
5. **Blocked Passage** - Restricted access points (gates, barriers)
6. **Enhanced Metadata** - Route numbers, route names, street names, place names

## Quick Start

### Basic Usage (Metadata Only, No External API Calls)

```python
# In factory_analysis.py

NRN_CONFIG = {
    'INCLUDE_ALLEYWAYS': False,
    'INCLUDE_METADATA': True,           # ✅ Extract route numbers, names from GPKG
    'INCLUDE_METADATA_LAYERS': False,   # ❌ Don't fetch from API
}

# This will add:
# - ROUTE_NUMBERS: "1,16" 
# - ROUTE_NAMES: "Trans-Canada Highway"
# - STREET_NAME: "Main Street"
# - PLACE_NAME: "Vancouver"
```

### Full Integration (All Features + API)

```python
NRN_CONFIG = {
    'INCLUDE_ALLEYWAYS': True,          # ✅ Fetch alleyways from MapServer
    'INCLUDE_METADATA': True,           # ✅ Extract route numbers, names
    'INCLUDE_METADATA_LAYERS': True,    # ✅ Fetch Trans-Canada, NHS, etc.
    'METADATA_LAYERS': [                # Specify which layers to fetch
        'trans_canada',
        'national_highway',
        'major_roads',
        'blocked_passage'
    ],
}

# This will add all metadata fields plus:
# - IS_TRANS_CANADA: True/False
# - IS_NATIONAL_HIGHWAY: True/False
# - IS_MAJOR_ROAD: True/False
# - HAS_BLOCKED_PASSAGE: True/False
# - BLOCKED_PASSAGE_TYPE: "Permanently Fixed" / "Removable"
```

## Features

### 1. Alleyways Integration

**Purpose**: Add complete alley/lane network for urban routing

**Benefits**:
- Last-mile access in dense urban areas
- Delivery route optimization
- Emergency vehicle access paths
- Complete network topology

**Implementation**:
```python
NRN_CONFIG['INCLUDE_ALLEYWAYS'] = True
```

**Default Values**:
- `ROADCLASS`: "Alleyway"
- `SPEED`: 15 km/h (configurable via `ALLEY_SPEED_DEFAULT`)
- `TRAFFICDIR`: "Both Directions"
- `PAVSURF`: "Paved"
- `ROADJURIS`: "Municipal"

### 2. Route Numbers & Names

**Purpose**: Extract highway/route designations from NRN data

**Benefits**:
- Route-specific queries ("fastest via Hwy 1")
- User-friendly navigation instructions
- Highway identification

**Fields Added**:
- `ROUTE_NUMBERS`: Combined route numbers (e.g., "1,16,99")
- `ROUTE_NAMES`: Combined route names (e.g., "Trans-Canada Highway,Sea to Sky Highway")

**Implementation**:
```python
NRN_CONFIG['INCLUDE_METADATA'] = True
```

**Source**: RTNUMBER1-5, RTENAME1-4EN fields from GPKG

### 3. Street & Place Names

**Purpose**: Extract street and municipality names

**Benefits**:
- Address-based routing
- Location-specific filtering
- Geocoding support

**Fields Added**:
- `STREET_NAME`: Left/right street name
- `PLACE_NAME`: City/municipality name

**Implementation**:
```python
NRN_CONFIG['INCLUDE_METADATA'] = True
```

**Source**: L_STNAME_C, R_STNAME_C, L_PLACENAM, R_PLACENAM from GPKG

### 4. Trans-Canada Highway Designation

**Purpose**: Flag segments that are part of the Trans-Canada Highway

**Benefits**:
- Prefer/avoid TCH routes
- Special styling for TCH on maps
- Tourism/cross-country routing

**Field Added**:
- `IS_TRANS_CANADA`: Boolean (True for TCH segments)

**Implementation**:
```python
NRN_CONFIG['INCLUDE_METADATA_LAYERS'] = True
NRN_CONFIG['METADATA_LAYERS'] = ['trans_canada']
```

**Source**: MapServer Layer 35

### 5. National Highway System

**Purpose**: Flag segments designated as part of Canada's NHS

**Benefits**:
- Identify nationally significant routes
- Long-distance routing preference
- Highway system analysis

**Field Added**:
- `IS_NATIONAL_HIGHWAY`: Boolean (True for NHS segments)

**Implementation**:
```python
NRN_CONFIG['INCLUDE_METADATA_LAYERS'] = True
NRN_CONFIG['METADATA_LAYERS'] = ['national_highway']
```

**Source**: MapServer Layer 49

### 6. Major Roads Designation

**Purpose**: Flag principal arterial roads

**Benefits**:
- Enhanced road classification
- Route quality scoring
- Traffic flow analysis

**Field Added**:
- `IS_MAJOR_ROAD`: Boolean (True for major roads)

**Implementation**:
```python
NRN_CONFIG['INCLUDE_METADATA_LAYERS'] = True
NRN_CONFIG['METADATA_LAYERS'] = ['major_roads']
```

**Source**: MapServer Layer 63

### 7. Blocked Passage Points

**Purpose**: Identify roads with gates, barriers, or restricted access

**Benefits**:
- Avoid gated communities
- Identify seasonal closures
- Restricted access routing

**Fields Added**:
- `HAS_BLOCKED_PASSAGE`: Boolean (True if segment has a blocked passage point)
- `BLOCKED_PASSAGE_TYPE`: "Permanently Fixed" or "Removable"

**Implementation**:
```python
NRN_CONFIG['INCLUDE_METADATA_LAYERS'] = True
NRN_CONFIG['METADATA_LAYERS'] = ['blocked_passage']
```

**Source**: MapServer Layer 2

## Performance Impact

| Feature | Memory | Processing Time | API Calls |
|---------|--------|-----------------|-----------|
| Metadata Extraction | <1 MB | <1 second | 0 |
| Alleyways | ~5 MB | ~10 seconds | 1 |
| Trans-Canada | ~1 MB | ~5 seconds | 1 |
| National Highway | ~1 MB | ~5 seconds | 1 |
| Major Roads | ~2 MB | ~5 seconds | 1 |
| Blocked Passage | <1 MB | ~2 seconds | 1 |
| **Total (All)** | **~10 MB** | **~30 seconds** | **5** |

**Overall Impact**: <2% increase in build time, <2% increase in memory

## Configuration Reference

```python
NRN_CONFIG = {
    # Core features
    'INCLUDE_ALLEYWAYS': False,          # Fetch alleyways from MapServer
    'INCLUDE_METADATA': True,            # Extract route numbers, names from GPKG
    'INCLUDE_METADATA_LAYERS': False,    # Fetch metadata layers from MapServer
    
    # Metadata layers (only used if INCLUDE_METADATA_LAYERS=True)
    'METADATA_LAYERS': [
        'trans_canada',       # Layer 35 - Trans-Canada Highway
        'national_highway',   # Layer 49 - National Highway System  
        'major_roads',        # Layer 63 - Major roads
        'blocked_passage',    # Layer 2 - Blocked passage points
        # 'local_roads'       # Layer 77 - Local roads (redundant with main data)
    ],
    
    # Speed settings
    'ALLEY_SPEED_DEFAULT': 15,  # km/h for alleyways
}
```

## Error Handling

All features are designed with graceful fallback:

```python
# If API fetch fails, processing continues without that layer
# Example output:
"""
🌐 Fetching Trans-Canada Highway from NRN MapServer...
   Attempt 1/3...
   ❌ All 3 attempts failed
   ⚠️  Trans-Canada Highway fetch failed - continuing without it

# Main road processing continues...
✅ DATA LOADING COMPLETE
   Total segments: 263,584
"""
```

## Use Cases

### Use Case 1: Route-Specific Queries

```python
# Find fastest route via Trans-Canada Highway only
tch_roads = gdf_roads[gdf_roads['IS_TRANS_CANADA'] == True]
G_tch = build_graph(tch_roads)
route = find_shortest_path(G_tch, origin, destination)
```

### Use Case 2: Avoid Restricted Access

```python
# Filter out roads with blocked passages
public_roads = gdf_roads[gdf_roads['HAS_BLOCKED_PASSAGE'] == False]
G_public = build_graph(public_roads)
route = find_shortest_path(G_public, origin, destination)
```

### Use Case 3: Urban Last-Mile Routing

```python
# Use alleys for final approach in dense areas
downtown_roads = gdf_roads[gdf_roads['PLACE_NAME'] == 'Vancouver']
# downtown_roads includes alleyways for complete coverage
route = find_shortest_path(G, depot, customer_address)
```

### Use Case 4: Highway Identification

```python
# Identify which highway a route uses
route_segments = gdf_roads.loc[route_edges]
highways = route_segments[route_segments['ROUTE_NUMBERS'].notna()]['ROUTE_NUMBERS'].unique()
print(f"Route uses highways: {', '.join(highways)}")
# Output: "Route uses highways: 1, 16, 99"
```

## Testing

Run the test suite:

```bash
python3 test_nrn_integration.py
```

Expected output:
```
================================================================================
NRN DATA LOADER - TEST SUITE
================================================================================

test_harmonize_alleyways_schema ... ✅ Schema harmonization test passed
test_merge_datasets ... ✅ Dataset merge test passed
test_extract_metadata ... ✅ Metadata extraction test passed
test_alleyway_speed_default_in_config ... ✅ Factory integration config test passed
test_alleyway_in_local_road_classes ... ✅ Alleyway classification test passed

================================================================================
TEST SUMMARY
================================================================================
Tests run: 5
Successes: 5
Failures: 0
Errors: 0

✅ ALL TESTS PASSED
```

## Troubleshooting

### Issue: API fetch fails

**Symptom**: `❌ All 3 attempts failed`

**Cause**: Network access blocked or API unavailable

**Solution**: 
1. Check network connectivity
2. Verify API endpoint is accessible
3. Disable API features if network is restricted:
   ```python
   NRN_CONFIG['INCLUDE_ALLEYWAYS'] = False
   NRN_CONFIG['INCLUDE_METADATA_LAYERS'] = False
   ```

### Issue: Spatial join takes too long

**Symptom**: Enrichment step hangs or times out

**Cause**: Large datasets with many segments

**Solution**: 
1. Reduce number of metadata layers
2. Filter main roads by bounding box first
3. Increase buffer tolerance

### Issue: Missing fields in output

**Symptom**: Expected fields like `IS_TRANS_CANADA` don't exist

**Cause**: Metadata layers not enabled or API fetch failed

**Solution**: Check configuration and logs for errors

## API Reference

### NRNDataLoader Class

```python
class NRNDataLoader:
    def __init__(self)
    
    def load_main_roads(self, gpkg_filename, layer_name, columns=None)
    def fetch_alleyways(self, timeout=60, max_retries=3)
    def fetch_layer_data(self, layer_id, layer_name, timeout=60, max_retries=3)
    def fetch_metadata_layers(self, layers=None, timeout=60, max_retries=3)
    
    def harmonize_alleyways_schema(self, gdf_alleys)
    def merge_datasets(self, gdf_roads, gdf_alleys)
    def enrich_with_metadata_layers(self, gdf_roads, metadata_layers)
    def extract_metadata(self, gdf)
    
    def load_and_merge_all(self, gpkg_filename, layer_name, 
                          columns=None,
                          include_alleyways=True,
                          include_metadata=True, 
                          include_metadata_layers=False,
                          metadata_layer_list=None)
```

## Resources

- **NRN MapServer**: https://geo.statcan.gc.ca/geo_wa/rest/services/NRN-RRN/nrn_rrn/MapServer
- **Feasibility Assessment**: See `ALLEYWAYS_FEASIBILITY.md`
- **Main Documentation**: See `README.md`

## License

See [LICENSE](LICENSE) file.

---

**Version**: 13.0  
**Date**: 2024-12-04  
**Status**: ✅ Production Ready
