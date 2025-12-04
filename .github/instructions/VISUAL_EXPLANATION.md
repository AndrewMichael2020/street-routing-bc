# Visual Explanation of the Fix

## Before Fix: Invalid Graph Structure

```
Highway 1 (Divided, 110 km/h)
Original NRN data has two separate road segments:

Segment A (Northbound): TRAFFICDIR = "Same Direction"
Node 1 -----> Node 2

Segment B (Southbound): TRAFFICDIR = "Opposite Direction"
Node 1 <----- Node 2

FAULTY CONVERSION LOGIC:
G.to_undirected() → G.to_directed()

Result: BOTH segments become bidirectional!
Node 1 <====> Node 2  (Northbound segment)
Node 1 <====> Node 2  (Southbound segment)

PROBLEM: Router sees 2 bidirectional edges but may pick the "wrong" one,
creating routes that travel north in the southbound lane (impossible in reality).
This causes the router to avoid highways as "unreliable".
```

## After Fix: Correct Graph Structure

```
Highway 1 (Divided, 110 km/h)
Original NRN data has two separate road segments:

Segment A (Northbound): TRAFFICDIR = "Same Direction"
Segment B (Southbound): TRAFFICDIR = "Opposite Direction"

FIXED CONVERSION LOGIC:
if TRAFFICDIR == "Same Direction":
    add_edge(u, v)  # Forward only
elif TRAFFICDIR == "Opposite Direction":
    add_edge(v, u)  # Reverse only

Result: Each segment is one-way!
Node 1 -----> Node 2  (Northbound lane, Segment A)
Node 1 <----- Node 2  (Southbound lane, Segment B)

SOLUTION: Router sees 2 separate one-way lanes, can confidently route
northbound traffic on northbound lane, southbound on southbound lane.
Highways are now "reliable" and preferred over local roads.
```

## Example Route Calculation

### Scenario: Vancouver to Abbotsford (~60 km east)

**Before Fix:**
```
Router considers:
Option 1: Highway 1 (divided, 110 km/h)
  - Risk: Might be a "trap" (bidirectional edges confusing)
  - Estimated time: UNRELIABLE
  
Option 2: Fraser Highway (local, 40 km/h)
  - Risk: Safe, predictable bidirectional road
  - Estimated time: 90 minutes (60km / 40 km/h)

Decision: Choose Fraser Highway (safe)
Result: 90-minute route on local streets ❌
```

**After Fix:**
```
Router considers:
Option 1: Highway 1 Eastbound Lane (one-way, 110 km/h)
  - Risk: None, proper one-way edge
  - Estimated time: 33 minutes (60km / 110 km/h)
  
Option 2: Fraser Highway (local, 40 km/h)
  - Risk: None, bidirectional road
  - Estimated time: 90 minutes (60km / 40 km/h)

Decision: Choose Highway 1 (faster)
Result: 33-minute route on highway ✅
```

## Graph Edge Comparison

### Local Road (Fraser Highway)
```
TRAFFICDIR: "Both Directions"

Node A <====> Node B
           
Both directions allowed, creates 2 edges:
1. A -> B (40 km/h, 15 min/10km)
2. B -> A (40 km/h, 15 min/10km)
```

### Divided Highway (Highway 1)
```
TRAFFICDIR: "Same Direction" (Eastbound lane)
TRAFFICDIR: "Opposite Direction" (Westbound lane)

Node A -----> Node B (Eastbound)
       <----- (Westbound)

One direction per segment, creates 2 edges:
1. A -> B (110 km/h, 5.45 min/10km) - Eastbound lane
2. B -> A (110 km/h, 5.45 min/10km) - Westbound lane

CRITICAL: These are separate NRN segments with different geometries!
```

## Cost Function Impact

### Travel Time Calculation
```python
time_minutes = (length_km / speed_kph) * 60
```

**10km Highway Segment:**
- Speed: 110 km/h
- Time: (10 / 110) * 60 = 5.45 minutes
- Cost: 5.45

**10km Local Road Segment:**
- Speed: 40 km/h  
- Time: (10 / 40) * 60 = 15.0 minutes
- Cost: 15.0

**Dijkstra's Algorithm:**
```
Chooses minimum cost path
5.45 < 15.0 → Highway wins ✅
```

## The "Trap" Scenario (Before Fix)

```
Router tries to go East on Highway 1:

Step 1: Enter Highway at Node A via on-ramp
Step 2: Travel to Node B (10km east)
Step 3: Try to exit at Node B via off-ramp

PROBLEM: Node B's edges are bidirectional mess
- Edge 1: B -> C (might be westbound disguised as eastbound)
- Edge 2: B -> C (might be eastbound disguised as westbound)
- Router doesn't know which is "real"

RESULT: Router avoids Highway 1 entirely, stays on local roads
```

## The Solution (After Fix)

```
Router tries to go East on Highway 1:

Step 1: Enter Highway at Node A via on-ramp
Step 2: Travel eastbound one-way edge A -> B
Step 3: Exit at Node B via off-ramp

SUCCESS: 
- Only eastbound edges exist from A -> B
- No confusion, no traps
- Router confidently uses Highway 1

RESULT: Routes follow highways as expected ✅
```

## Real-World Analogy

**Before Fix:** Like GPS showing a highway as a two-way street
- Navigation system unsure which lane goes which direction
- Avoids highway to prevent wrong-way driving
- Takes local roads instead (slower but predictable)

**After Fix:** Like GPS correctly showing divided highway lanes
- Navigation system knows northbound from southbound lanes
- Confidently routes on correct lane
- Uses highway for faster travel times

## Summary

The fix changes how the routing engine interprets divided highways:

| Aspect | Before | After |
|--------|--------|-------|
| **Highway Lanes** | Bidirectional edges | One-way edges |
| **Router Trust** | Low (avoids highways) | High (prefers highways) |
| **Route Quality** | Local roads (slow) | Highways (fast) |
| **Travel Time** | 90 min | 33 min |
| **Realism** | ❌ Unrealistic | ✅ Realistic |

The simple addition of TRAFFICDIR handling transforms the graph from an unreliable representation to an accurate model of BC's road network.
