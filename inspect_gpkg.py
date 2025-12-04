#!/usr/bin/env python3
"""
inspect_gpkg.py

Small helper to inspect a GeoPackage (.gpkg) file: list layers, show schema/CRS,
preview the first few rows and optionally compute value counts for key columns.

Usage:
  python inspect_gpkg.py /path/to/NRN_BC_14_0_GPKG_en.gpkg
  python inspect_gpkg.py /path/to/file.gpkg --layer roads --full-stats

The script avoids reading entire large layers by default; use --full-stats
only if you expect to run this locally and have memory to spare.


python3 inspect_gpkg.py NRN_BC_14_0_GPKG_en.gpkg
python3 inspect_gpkg.py NRN_BC_14_0_GPKG_en.gpkg --layer NRN_BC_14_0_BLKPASSAGE --sample 10
python3 inspect_gpkg.py NRN_BC_14_0_GPKG_en.gpkg --layer NRN_BC_14_0_FERRYSEG --sample 10
python3 inspect_gpkg.py NRN_BC_14_0_GPKG_en.gpkg --layer NRN_BC_14_0_JUNCTION --sample 10
python3 inspect_gpkg.py NRN_BC_14_0_GPKG_en.gpkg --layer NRN_BC_14_0_ROADSEG --sample 10
python3 inspect_gpkg.py NRN_BC_14_0_GPKG_en.gpkg --layer NRN_BC_14_0_TOLLPOINT --sample 10
python3 inspect_gpkg.py /path/to/NRN_BC_14_0_GPKG_en.gpkg --layer NRN_BC_14_0_ROADSEG --full-stats
python3 inspect_gpkg.py /path/to/NRN_BC_14_0_GPKG_en.gpkg --layer NRN_BC_14_0_JUNCTION --full-stats
python3 inspect_gpkg.py /path/to/NRN_BC_14_0_GPKG_en.gpkg --layer NRN_BC_14_0_BLKPASSAGE --full-stats

"""

import argparse
import os
import sys
import time
from collections import Counter

try:
    import fiona
    import geopandas as gpd
except Exception as e:
    print("Missing dependency: please install geopandas and fiona (see requirements.txt)")
    raise


def inspect_gpkg(path, layer=None, sample=5, full_stats=False):
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return 2

    print("File:", path)
    print("Listing layers...")
    try:
        layers = fiona.listlayers(path)
    except Exception as e:
        print("Error listing layers:", e)
        return 3

    print("  Layers found:")
    for i, l in enumerate(layers):
        print(f"    {i+1}. {l}")

    if layer is None:
        # default to the first layer
        if len(layers) == 0:
            print("No layers found in geopackage.")
            return 0
        layer = layers[0]

    if layer not in layers:
        print(f"Layer '{layer}' not found in file. Available layers: {layers}")
        return 4

    print(f"\nInspecting layer: {layer}\n")

    start = time.time()
    try:
        # Use fiona to get schema and CRS cheaply
        with fiona.open(path, layer=layer) as src:
            schema = src.schema
            crs = src.crs
            try:
                count = len(src)
            except Exception:
                # some fiona backends may not support len cheaply
                count = None

            print("Schema properties (columns):")
            props = schema.get('properties', {}) if schema else {}
            for k, v in props.items():
                print(f"  - {k}: {v}")

            print("CRS:", crs)
            if count is not None:
                print("Rows:", count)
            else:
                print("Rows: unknown (use --full-stats to count)")

            # show first `sample` rows using geopandas for nice printing
            try:
                gdf = gpd.read_file(path, layer=layer)
                print(f"\nPreview (first {sample} rows):")
                print(gdf.head(sample).to_string(index=False))
            except Exception as e:
                print("Could not read layer with geopandas for preview:", e)

    except Exception as e:
        print("Error opening layer:", e)
        return 5

    elapsed = time.time() - start
    print(f"\nFinished quick inspection in {elapsed:.2f}s")

    if full_stats:
        print("\nComputing full stats for selected columns (this may take time)")
        stats_cols = ['TRAFFICDIR', 'PAVSURF', 'ROADCLASS', 'SPEED']
        counts = {c: Counter() for c in stats_cols}
        total = 0
        with fiona.open(path, layer=layer) as src:
            for feat in src:
                props = feat.get('properties', {})
                for c in stats_cols:
                    counts[c][props.get(c)] += 1
                total += 1

        print(f"Rows counted: {total}")
        for c in stats_cols:
            print(f"\nColumn: {c}")
            most = counts[c].most_common(10)
            if len(most) == 0:
                print("  (no values found)")
            else:
                for val, cnt in most:
                    print(f"  {val!r}: {cnt}")

    return 0


def main():
    p = argparse.ArgumentParser(description="Inspect a GeoPackage (.gpkg) file")
    p.add_argument('path', help='Path to .gpkg file')
    p.add_argument('--layer', '-l', help='Specific layer to inspect (default: first)')
    p.add_argument('--sample', '-n', type=int, default=5, help='Number of rows to preview')
    p.add_argument('--full-stats', action='store_true', help='Compute full value counts for key columns')

    args = p.parse_args()
    rc = inspect_gpkg(args.path, layer=args.layer, sample=args.sample, full_stats=args.full_stats)
    sys.exit(rc)


if __name__ == '__main__':
    main()
