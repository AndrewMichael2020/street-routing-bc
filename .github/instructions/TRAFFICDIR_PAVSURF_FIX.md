# TRAFFICDIR and PAVSURF Fix - Issue #7

## Overview

This update addresses the issue where TRAFFICDIR and PAVSURF attributes were showing as "Unknown" in the route audit output. The fix includes:

1. **Enhanced diagnostics** to identify data quality issues
2. **Inference logic** to improve missing values
3. **Targeted route generation** for better testing (5 average + 5 edge cases)
4. **Comprehensive audit output** showing all route metadata

## Changes Made

### 1. factory_analysis.py

#### Added Data Quality Diagnostics (after line 56)
- Shows percentage of known vs unknown values for TRAFFICDIR, PAVSURF, ROADCLASS
- Displays top values for each field
- Reports field loading status

#### Added Inference Logic (new section D2)
Three inference rules to improve data quality:

1. **PAVSURF from PAVSTATUS**: If PAVSTATUS is "Paved" but PAVSURF is "Unknown", set PAVSURF to "Paved"
2. **Major Roads Assumption**: Major roads (Freeway, Expressway, Arterial, Collector) with Unknown PAVSURF are assumed to be "Paved"
3. **Local Roads Directionality**: Local roads (Local, Collector, Resource, Ferry) with Unknown TRAFFICDIR are assumed to be "Both Directions"

#### Added Final Statistics (section 6)
- Reports percentage of edges with known TRAFFICDIR, PAVSURF, and ROADCLASS values after all processing

### 2. production_simulation.py

#### Targeted Route Generation (section 2)
Replaced random route generation with targeted routes:

**5 Average Distance Routes:**
- 15 km route
- 30 km route
- 45 km route
- 60 km route
- 75 km route

**5 Edge Case Routes:**
- Very short (~5 km) - local urban route
- Long distance (~80 km) - to Abbotsford area
- Cross-region (~50 km) - Vancouver to Surrey
- Coastal route - Richmond to North Vancouver via bridges
- Extreme distance - North Vancouver to eastern suburbs

#### Enhanced Route Audit (section 7-9)
- Shows detailed segment information for all routes
- Displays road class distribution with percentages
- Shows surface type distribution
- Reports segment count and route statistics
- Comprehensive output format with proper column widths

#### Sample Output Format:
```
SEG  | CLASS              | TRAFFICDIR         | SURFACE      | SPEED    | DIST (m)   | TIME (min)
-----------------------------------------------------------------------------------------------------
1    | Freeway            | Same Direction     | Paved        | 110.0    | 1000.0     | 0.55      
2    | Arterial           | Both Directions    | Paved        | 60.0     | 1000.0     | 1.00      
```

## Why TRAFFICDIR and PAVSURF Show as "Unknown"

The "Unknown" values come from the source NRN dataset itself, which has incomplete data:

1. **TRAFFICDIR**: Many highway segments don't have directionality information in the NRN data
2. **PAVSURF**: Many road segments don't have surface type information in the NRN data

### What This Fix Does

Instead of leaving these as "Unknown", the fix:

1. **Infers from other fields**: Uses PAVSTATUS to determine PAVSURF when possible
2. **Makes reasonable assumptions**: 
   - Major roads (Freeway, Expressway, etc.) → assumed Paved
   - Local roads → assumed Both Directions (bidirectional)
3. **Reports data quality**: Shows exactly how many values are known vs unknown

### What Still Shows as "Unknown"

- **Highway TRAFFICDIR**: Intentionally left as "Unknown" when not specified in source data, as inferring directionality for divided highways could be dangerous
- **Minor roads PAVSURF**: Some minor roads may still show "Unknown" if they don't match the inference rules

These "Unknown" values are treated conservatively:
- Unknown TRAFFICDIR → treated as "Both Directions" (bidirectional) in routing logic
- Unknown PAVSURF → treated as "Paved" in speed calculations (optimistic assumption)

## Testing

### Run the synthetic test:
```bash
python3 test_enhanced_output.py
```

This verifies that GraphML save/load preserves all attributes.

### Run with real data:

1. **Build the graph:**
```bash
python3 factory_analysis.py
```

Expected output:
```
   Data Quality Check:
     TRAFFICDIR     : XXX,XXX known (XX.X%), XXX,XXX unknown
     PAVSURF        : XXX,XXX known (XX.X%), XXX,XXX unknown
     ROADCLASS      : XXX,XXX known (XX.X%), XXX,XXX unknown
   
   Inferring missing values...
     Inferred XXX PAVSURF values from PAVSTATUS
     Inferred XXX PAVSURF values for major roads (assumed Paved)
     Inferred XXX TRAFFICDIR values for local roads (assumed Both Directions)
```

2. **Run simulation:**
```bash
python3 production_simulation.py
```

Expected output shows 10 detailed route audits with:
- Road class distribution
- Surface distribution
- Segment-by-segment breakdown
- Summary statistics

## Expected Results

After running the pipeline, you should see:

1. **Better coverage**: Higher percentage of non-Unknown values for TRAFFICDIR and PAVSURF
2. **Detailed diagnostics**: Clear reporting of data quality at each stage
3. **Comprehensive audits**: All 10 routes audited with full metadata
4. **Realistic values**: Where inference is applied, values match road classification

## Files Modified

- `factory_analysis.py`: Added diagnostics and inference logic
- `production_simulation.py`: Complete rewrite of route generation and auditing
- `test_enhanced_output.py`: New test file for validation

## Next Steps

If you still see many "Unknown" values after these changes, it indicates:

1. The source NRN data has very incomplete metadata
2. You may need to obtain a different version of the NRN dataset
3. Or accept that some values will remain unknown and ensure the routing logic handles them correctly (which it does)

## Security

All changes maintain the existing security posture:
- No secrets or credentials
- No new dependencies
- No external API calls
- Safe data handling with conservative fallbacks
