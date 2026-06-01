# Structural Evaluation Report

**Date:** 2026-05-31 08:01:34
**Prompt:** generate grid

## Analysis Parameters

| Parameter | Value |
|-----------|-------|
| Material | TIMBER |
| Floor build-up (SDL) | 1.5 kN/m² |
| Live load | 2.0 kN/m² |
| Total applied load | 3.5 kN/m² |

## Structural Checks

```
Structural evaluation: PASS

BEAMS:
  A3-A5    120x300   L=3.75m  M=10.16kNm  S=5.645MPa  d_LL=3.815mm/10.417mm  ok
  A3-B3    100x240   L=3.2m  M=4.634kNm  S=4.827MPa  d_LL=2.963mm/8.889mm  ok
  A5-C5    100x240   L=3.5m  M=5.543kNm  S=5.774MPa  d_LL=4.24mm/9.722mm  ok
  B1-B3    100x240   L=1.75m  M=1.386kNm  S=1.444MPa  d_LL=0.265mm/4.861mm  ok
  B1-D1    100x240   L=2.6m  M=3.059kNm  S=3.186MPa  d_LL=1.291mm/7.222mm  ok
  C5-C7    100x240   L=1.8m  M=1.466kNm  S=1.527MPa  d_LL=0.297mm/5.0mm  ok
  C5-D5    100x240   L=2.3m  M=2.394kNm  S=2.493MPa  d_LL=0.791mm/6.389mm  ok
  C7-D7    100x240   L=2.3m  M=2.394kNm  S=2.493MPa  d_LL=0.791mm/6.389mm  ok
  D1-D2    100x240   L=1.5m  M=1.461kNm  S=1.522MPa  d_LL=0.207mm/4.167mm  ok
  D1-E1    100x240   L=3.5m  M=5.543kNm  S=5.774MPa  d_LL=4.24mm/9.722mm  ok
  D2-D3    100x240   L=0.25m  M=0.041kNm  S=0.042MPa  d_LL=0.0mm/0.694mm  ok
  D2-E2    100x240   L=3.5m  M=5.543kNm  S=5.774MPa  d_LL=4.24mm/9.722mm  ok
  D3-D5    100x240   L=3.75m  M=9.132kNm  S=9.512MPa  d_LL=8.103mm/10.417mm  ok
  D5-D6    100x240   L=0.75m  M=0.365kNm  S=0.38MPa  d_LL=0.013mm/2.083mm  ok
  D6-D7    100x240   L=1.05m  M=0.716kNm  S=0.746MPa  d_LL=0.05mm/2.917mm  ok
  D6-E6    100x240   L=3.5m  M=5.543kNm  S=5.774MPa  d_LL=4.24mm/9.722mm  ok
  E1-E2    100x240   L=1.5m  M=1.756kNm  S=1.83MPa  d_LL=0.25mm/4.167mm  ok
  E2-E4    100x240   L=1.7m  M=2.256kNm  S=2.35MPa  d_LL=0.413mm/4.722mm  ok
  E2-G2    100x240   L=3.8m  M=6.534kNm  S=6.806MPa  d_LL=5.892mm/10.556mm  ok
  E4-E6    100x240   L=3.05m  M=7.262kNm  S=7.564MPa  d_LL=4.279mm/8.472mm  ok
  E4-F4    100x240   L=3.5m  M=5.543kNm  S=5.774MPa  d_LL=4.24mm/9.722mm  ok
  E6-E7    100x240   L=1.05m  M=0.861kNm  S=0.896MPa  d_LL=0.06mm/2.917mm  ok
  E7-F7    100x240   L=3.5m  M=5.543kNm  S=5.774MPa  d_LL=4.24mm/9.722mm  ok
  F4-F7    100x240   L=4.1m  M=7.607kNm  S=7.923MPa  d_LL=7.985mm/11.389mm  ok
  F4-G4    100x240   L=0.3m  M=0.041kNm  S=0.042MPa  d_LL=0.0mm/0.833mm  ok
  G2-G4    100x240   L=1.7m  M=1.308kNm  S=1.362MPa  d_LL=0.236mm/4.722mm  ok
  B3-C3    100x240   L=2.6m  M=3.059kNm  S=3.186MPa  d_LL=1.291mm/7.222mm  ok

COLUMNS:
  A3       100x100   H=3.5m  P=4.94kN  S=0.4935MPa  SF=25.76  ok
  A5       100x100   H=3.5m  P=8.71kN  S=0.8715MPa  SF=14.59  ok
  B1       100x100   H=3.5m  P=4.77kN  S=0.4769MPa  SF=26.66  ok
  B3       100x100   H=3.5m  P=5.38kN  S=0.5381MPa  SF=23.62  ok
  C5       100x100   H=3.5m  P=7.11kN  S=0.7114MPa  SF=17.87  ok
  C7       100x100   H=3.5m  P=3.67kN  S=0.3675MPa  SF=34.59  ok
  D1       100x100   H=3.5m  P=7.79kN  S=0.7787MPa  SF=16.32  ok
  D2       100x100   H=3.5m  P=9.06kN  S=0.9056MPa  SF=14.04  ok
  D3       100x100   H=3.5m  P=8.8kN  S=0.8803MPa  SF=14.44  ok
  D5       100x100   H=3.5m  P=15.65kN  S=1.5654MPa  SF=8.12  ok
  D6       100x100   H=3.5m  P=9.31kN  S=0.931MPa  SF=13.66  ok
  D7       100x100   H=3.5m  P=5.5kN  S=0.5504MPa  SF=23.1  ok
  E1       100x100   H=3.5m  P=9.36kN  S=0.9363MPa  SF=13.58  ok
  E2       100x100   H=3.5m  P=10.89kN  S=1.0894MPa  SF=11.67  ok
  E4       100x100   H=3.5m  P=23.14kN  S=2.3144MPa  SF=5.49  ok
  E6       100x100   H=3.5m  P=11.2kN  S=1.12MPa  SF=11.35  ok
  E7       100x100   H=3.5m  P=6.61kN  S=0.6606MPa  SF=19.24  ok
  F4       100x100   H=3.5m  P=12.64kN  S=1.2644MPa  SF=10.05  ok
  F7       100x100   H=3.5m  P=3.67kN  S=0.3675MPa  SF=34.59  ok
  G2       100x100   H=3.5m  P=3.67kN  S=0.3675MPa  SF=34.59  ok
  G4       100x100   H=3.5m  P=3.67kN  S=0.3675MPa  SF=34.59  ok
```

## Change Summary

Removed columns C3 and beams C3-C5, C3-D3 to reduce load on the structure.

## Cost & Flexibility Analysis

| Metric | Value |
|--------|-------|
| Material added | +$0 |
| Material saved | -$144 |
| Net cost change | $-144 |
| Disruption | Significant (6/10) |
| Spatial Penalty | 0.00 |
| Flexibility | 1.0/10 — Very Low |

> 3 removed | Saved: -$144 | Flexibility: 1.0/10 (Very Low) | Disruption: 6/10 (Significant)
