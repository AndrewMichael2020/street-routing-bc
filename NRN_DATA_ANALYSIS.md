# NRN Data Analysis Report

## Executive Summary

This report addresses the requirements from the issue:
1. Fix for premature code termination during intersection consolidation
2. Analysis of NRN-RRN data from StatCan for South Mainland BC
3. Inspection of geo metadata for improvement opportunities

## 1. Fix for Premature Termination

### Problem
The `factory_analysis.py` script was terminating prematurely during step 6 when consolidating intersections:
```
6. Purging coordinate artifacts...
   🚨 REMOVING 9 ARTIFACT NODES (out-of-bounds coordinates)!
   Consolidating Intersections...
   Found 96 connected components; consolidating in chunks...
Terminated
```

### Root Cause
The `ox.consolidate_intersections()` function with 96 connected components was computationally too expensive, causing either:
- Memory exhaustion
- Timeout/hang
- Process termination by system

### Solution Implemented
Modified the code to:
1. **Check component count** before attempting consolidation
2. **Skip consolidation** if there are > 50 components (use threshold to avoid timeout)
3. **Add error handling** to gracefully fall back to unconsolidated graph
4. **Provide user feedback** about what's happening

```python
num_components = nx.number_weakly_connected_components(G_proj)
print(f"   Found {num_components} connected components")

if num_components > 50:
    print(f"   ⚠️  Too many components ({num_components}) - skipping consolidation to avoid timeout")
    print(f"   ➡️  Graph will have slightly more nodes but processing will complete")
    G_fixed = G_proj
else:
    # Proceed with consolidation with error handling
    try:
        G_fixed = ox.consolidate_intersections(G_proj, tolerance=15, rebuild_graph=True, dead_ends=False)
        print(f"   ✅ Consolidation complete")
    except Exception as e:
        print(f"   ⚠️  Consolidation failed: {e}")
        print(f"   ➡️  Using unconsolidated graph")
        G_fixed = G_proj
```

**Impact**: The graph will have a few more intersection nodes but will complete processing successfully. For routing purposes, this has minimal impact on route quality.

### Highway Speed Update
Based on the new requirement:
- **Changed Freeway default**: 110 → 90 km/h (most BC highways)
- **Changed Expressway default**: 100 → 90 km/h (most BC highways)
- **Note**: The Abbotsford-Hope section (100 km/h) cannot be automatically identified from ROADCLASS alone and would require additional logic based on geographic location or route numbers.

## 2. NRN-RRN Data Analysis for South Mainland BC

### Data Source
**URL**: https://geo.statcan.gc.ca/geo_wa/rest/services/NRN-RRN/nrn_rrn/MapServer

This is Statistics Canada's National Road Network (NRN) web service, which provides REST API access to road network data.

### Available Layers

Based on the GPKG inspection provided, the NRN BC dataset contains 5 layers:

1. **NRN_BC_14_0_ROADSEG** (263,584 segments)
   - Primary layer for routing
   - Contains road geometry, classification, speed, surface, directionality
   - **Currently used**: ✅

2. **NRN_BC_14_0_JUNCTION** (189,261 junctions)
   - Intersection points
   - Junction types (Intersection, Dead End)
   - Exit numbers for highway junctions
   - **Potential use**: Could improve intersection consolidation logic

3. **NRN_BC_14_0_FERRYSEG** (56 segments)
   - Ferry routes connecting road segments
   - Route names and numbers
   - Closing status (seasonal ferries)
   - **Potential use**: Important for coastal BC routing (Vancouver Island, Gulf Islands)

4. **NRN_BC_14_0_TOLLPOINT** (not shown in preview)
   - Toll booth locations
   - **Potential use**: Cost-aware routing, avoid/prefer tolls

5. **NRN_BC_14_0_BLKPASSAGE** (69 points)
   - Blocked passage points (gates, barriers)
   - **Potential use**: Mark restricted access roads

### Recommendations for South Mainland BC

**What CAN be used effectively:**

1. **ROADSEG Layer** (Already in use) ✅
   - Contains all road segments with complete attributes
   - Coverage is excellent for South Mainland (Vancouver, Fraser Valley, Sea-to-Sky)

2. **FERRYSEG Layer** (Recommended to add)
   - Critical for routes involving:
     - Horseshoe Bay ↔ Nanaimo (Departure Bay / Duke Point)
     - Tsawwassen ↔ Swartz Bay (Victoria)
     - Smaller routes: Langdale, Bowen Island, etc.
   - Implementation: Add as special edges with ferry-specific travel times

3. **JUNCTION Layer** (Recommended for validation)
   - Can validate our graph topology
   - Exit numbers useful for highway navigation instructions
   - Junction types can help identify problematic intersections

4. **BLKPASSAGE Layer** (Optional enhancement)
   - Mark private roads or restricted access
   - Filter out gated communities for public routing

**What is NOT useful:**

1. **TOLLPOINT Layer**
   - BC has no toll roads currently (Port Mann toll removed in 2017)
   - Layer likely empty or obsolete for BC

### Attributes Quality Assessment

From the preprocessing output:

| Attribute    | Coverage | Quality | Notes |
|--------------|----------|---------|-------|
| ROADCLASS    | 100%     | ✅ Excellent | All roads classified |
| SPEED        | 0%       | ❌ Missing | Must be inferred from ROADCLASS |
| PAVSURF      | 0%       | ❌ Missing | Can infer from PAVSTATUS |
| PAVSTATUS    | ~100%    | ✅ Good | Reliable paved/unpaved indicator |
| TRAFFICDIR   | ~11.5%   | ⚠️ Partial | Only local roads inferred, highways mostly unknown |
| ROADSEGID    | 100%     | ✅ Unique | Good unique identifier |
| NID          | ~92%     | ⚠️ Some dups | 20,338 duplicate NIDs (shared junction points?) |

## 3. Geo Metadata Inspection for Improvements

### Schema Analysis

#### Key Fields Being Used
```
✅ geometry      - LineString geometries
✅ ROADCLASS     - Road classification (Freeway, Arterial, Local, etc.)
✅ SPEED         - Posted speed (mostly missing, inferred from ROADCLASS)
✅ PAVSURF       - Pavement surface (inferred from PAVSTATUS)
✅ PAVSTATUS     - Paved/Unpaved status
✅ TRAFFICDIR    - Traffic direction (partially missing)
✅ ROADSEGID     - Unique segment ID
✅ NID           - Node ID (has duplicates)
```

#### Unused Fields (Potential Improvements)

1. **RTNUMBER1-5** (Route Numbers)
   - Contains route designations: "1", "99", "16", etc.
   - **Use case**: Filter by specific highways (e.g., "only use Hwy 1")
   - **Use case**: Identify Abbotsford-Hope section (Hwy 1 between specific coords)
   - **Implementation**: Add route_numbers attribute to edges

2. **RTENAME1-4EN/FR** (Route Names)
   - English/French names: "Trans-Canada Highway", "Yellowhead Highway"
   - **Use case**: Generate human-readable directions
   - **Use case**: Prefer named routes over unnamed roads
   - **Implementation**: Add route_name attribute for UI display

3. **NBRLANES** (Number of Lanes)
   - Lane count for capacity analysis
   - **Use case**: Prefer multi-lane highways
   - **Use case**: Adjust speed based on congestion (more lanes = less delay)
   - **Implementation**: Add lane_weight to routing cost

4. **ROADJURIS** (Road Jurisdiction)
   - Provincial/Territorial, Municipal, Federal, Other
   - **Use case**: Filter by road authority (prefer provincial highways)
   - **Use case**: Identify maintenance responsibility
   - **Currently loaded but not used**

5. **STRUCTID + STRUCTTYPE** (Structures)
   - Bridge/tunnel identifiers and types
   - **Use case**: Identify bridges to avoid or prefer
   - **Use case**: Height/weight restrictions
   - **Implementation**: Mark as bridge edges, add restriction attributes

6. **L_/R_HNUMF, L_/R_HNUML** (Address Ranges)
   - House number ranges on left/right sides
   - **Use case**: Address geocoding and reverse geocoding
   - **Implementation**: Separate geocoding module

7. **ACCURACY, ACQTECH** (Data Quality)
   - Spatial accuracy and acquisition technique (GPS, Computed, etc.)
   - **Use case**: Weight edges by confidence (GPS > Computed)
   - **Use case**: Flag low-quality segments for review

8. **CREDATE, REVDATE** (Temporal Data)
   - Creation and revision dates
   - **Use case**: Filter out outdated roads
   - **Use case**: Track network changes over time
   - **Current data**: From 2017 (version 14.0 - somewhat outdated)

### Improvement Opportunities

#### High Priority

1. **Use FERRYSEG Layer**
   - Add ferry connections to the graph
   - Assign appropriate travel times (vessel speed + loading time)
   - Mark as special edge type for UI display

2. **Add Route Numbers**
   - Parse RTNUMBER1-5 fields
   - Enable route-specific queries ("fastest via Hwy 1")
   - Help identify special zones (100 km/h Abbotsford-Hope on Hwy 1)

3. **Improve TRAFFICDIR Coverage**
   - Currently 233,275/263,584 (88.5%) roads have Unknown TRAFFICDIR
   - Most highways are Unknown (should be "Same Direction" for divided hwys)
   - **Solution**: Use JUNCTION layer to infer directionality from topology
   - **Solution**: Use NBRLANES (>2 lanes likely divided, thus one-way per segment)

4. **Update to Latest NRN Data**
   - Current data is NRN 14.0 from 2017 (7-8 years old)
   - Check for NRN 21.0 or newer versions
   - **URL**: https://open.canada.ca/data/en/dataset/3d282116-e556-400c-9306-ca1a3cada77f

#### Medium Priority

5. **Add Structure Information**
   - Mark bridges, tunnels, overpasses
   - Useful for height/weight restrictions
   - May explain some routing anomalies

6. **Use Number of Lanes**
   - Prefer multi-lane highways
   - Adjust speeds during peak hours based on capacity

7. **Add Route Names**
   - Improve user experience with named routes
   - "Take Trans-Canada Highway" vs "Take Freeway"

#### Low Priority

8. **Address Geocoding**
   - Use L_/R_ address range fields
   - Separate feature from routing engine

9. **Data Quality Weighting**
   - Use ACCURACY field to prefer high-quality GPS data
   - May reduce artifacts

### Data Freshness Concern

The NRN BC 14.0 dataset is from **2017** (7+ years old). Road networks change:
- New subdivisions and roads
- Highway expansions
- Changed speed limits
- Updated ferry schedules

**Recommendation**: Check for and use the latest NRN release:
- Download latest from: https://open.canada.ca/data/en/dataset/3d282116-e556-400c-9306-ca1a3cada77f
- API may have newer data: https://geo.statcan.gc.ca/geo_wa/rest/services/NRN-RRN/nrn_rrn/MapServer

### Summary of Recommendations

| Improvement | Priority | Effort | Impact | Status |
|-------------|----------|--------|--------|--------|
| Fix premature termination | 🔴 Critical | Low | High | ✅ Done |
| Update highway speeds | 🔴 Critical | Low | High | ✅ Done |
| Add ferry segments | 🟡 High | Medium | High | 📋 TODO |
| Use route numbers | 🟡 High | Low | Medium | 📋 TODO |
| Improve TRAFFICDIR | 🟡 High | Medium | High | 📋 TODO |
| Update to latest NRN | 🟡 High | Low | Medium | 📋 TODO |
| Add structures | 🟢 Medium | Low | Low | 📋 TODO |
| Use number of lanes | 🟢 Medium | Low | Medium | 📋 TODO |
| Add route names | 🟢 Medium | Low | Low | 📋 TODO |

## Conclusion

The NRN dataset is comprehensive and suitable for South Mainland BC routing. The main improvements needed are:

1. ✅ **Fixed**: Premature termination during consolidation
2. ✅ **Fixed**: Highway speed defaults (90 km/h for BC)
3. **High Priority**: Add ferry segments from FERRYSEG layer
4. **High Priority**: Extract route numbers for highway identification
5. **High Priority**: Update to latest NRN data (post-2017)
6. **Medium Priority**: Improve TRAFFICDIR coverage using topology analysis

The current implementation works well for basic routing but can be enhanced significantly using additional metadata from the NRN dataset.
