# HotSpot v7 source snapshot

Source: https://github.com/uvahotspot/HotSpot (master archive downloaded 2026-10-08).
Archive URL: https://codeload.github.com/uvahotspot/HotSpot/zip/refs/heads/master
Archive SHA256: 3b3d96d8b82e68a9bd1b1179ee9284ca05653cb5a14d6439ba45c9a659c97a61

Only build sources/headers, Makefile, LICENSE, README and template configuration are included.
The upstream license is retained in full in LICENSE and source headers.
Local modification: grid temperature text output precision %.2f -> %.8f in
temperature_grid.c (steady/transient dump). No solver physics or tolerances changed.
This prevents .01 K output rounding from merging different Pareto candidates.
Build without optional SuperLU/BLAS: make hotspot SUPERLU=0.
