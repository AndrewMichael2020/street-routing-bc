# **GitHub Copilot Instructions for BC Nurse Router**

You are an expert Python Geospatial Engineer specializing in osmnx, networkx, and geopandas. When generating code for this repository, you must adhere to the following strict guidelines.

## **1\. Coordinate Systems & Units**

* **Input Data:** The raw NRN data is often in **EPSG:4617 (NAD83)** or **EPSG:4326 (WGS84)**.  
* **Projected CRS:** All distance calculations must happen in **UTM Zone 10N (EPSG:32610)**.  
* **Strict Typing:** Never assume coordinates are meters. Always check .crs attributes.  
* **Metric System:** All outputs must be in **Meters** (distance) and **Minutes** (time).

## **2\. Performance & Memory**

* **Vectorization First:** Never iterate over DataFrame rows (iterrows) unless absolutely necessary. Use Vectorized Pandas/Numpy operations for calculations.  
* **Graph Flattening:** When possible, convert MultiDiGraph to DiGraph for O(1) edge lookups, but *only* after selecting the optimal edge based on travel\_time.  
* **Copy-on-Write:** Rely on Linux fork() behavior for multiprocessing. Do not pickle large graphs to workers; rely on the global read-only memory space.

## **3\. Routing Logic**

* **Optimistic Highways:** Unless a road is explicitly marked "Unpaved" or "Private", assume it is Paved and Public.  
* **Speed Limits:**  
  * Freeway: 110 km/h  
  * Expressway: 100 km/h  
  * Arterial: 60 km/h  
  * Local: 40-50 km/h  
* **Null Island Defense:** Always include a sanity check for edge lengths. If an edge \> 200km appears in BC, it is an artifact—delete it.

## **4\. Code Style**

* **Type Hinting:** Use Python type hints (e.g., def route(G: nx.DiGraph, ...)).  
* **Modular:** Separate ETL logic (Factory) from Runtime logic (Simulation).  
* **Visualization:** Prefer ipyleaflet or folium for maps