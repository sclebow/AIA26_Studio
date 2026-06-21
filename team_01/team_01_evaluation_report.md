# Structural Evaluation Report

**Date:** 2026-06-21 10:38:29
**Prompt:** what if we remove beam A3-A5

## Analysis Parameters

| Parameter | Value |
|-----------|-------|
| Material | TIMBER |
| Floor build-up (SDL) | 3.5 kN/m² |
| Live load | 2.0 kN/m² |
| Total applied load | 5.5 kN/m² |

## Structural Checks

```
Structural evaluation: PASS

BEAMS:
  A3-A5    120x300   L=3.75m  M=15.785kNm  S=8.77MPa  d_LL=3.815mm/10.417mm  ok
  A3-B3    100x240   L=3.2m  M=7.194kNm  S=7.493MPa  d_LL=2.963mm/8.889mm  ok
  A5-C5    100x240   L=3.5m  M=8.606kNm  S=8.964MPa  d_LL=4.24mm/9.722mm  ok
  B1-B3    100x240   L=1.75m  M=2.151kNm  S=2.241MPa  d_LL=0.265mm/4.861mm  ok
  B1-D1    100x240   L=2.6m  M=4.749kNm  S=4.947MPa  d_LL=1.291mm/7.222mm  ok
  C5-C7    100x240   L=1.8m  M=2.276kNm  S=2.371MPa  d_LL=0.297mm/5.0mm  ok
  C5-D5    100x240   L=2.3m  M=3.716kNm  S=3.871MPa  d_LL=0.791mm/6.389mm  ok
  C7-D7    100x240   L=2.3m  M=3.716kNm  S=3.871MPa  d_LL=0.791mm/6.389mm  ok
  D1-D2    100x240   L=1.5m  M=2.277kNm  S=2.372MPa  d_LL=0.207mm/4.167mm  ok
  D1-E1    100x240   L=3.5m  M=8.606kNm  S=8.964MPa  d_LL=4.24mm/9.722mm  ok
  D2-E2    100x240   L=3.5m  M=8.606kNm  S=8.964MPa  d_LL=4.24mm/9.722mm  ok
  D5-D6    100x240   L=0.75m  M=0.569kNm  S=0.593MPa  d_LL=0.013mm/2.083mm  ok
  D6-D7    100x240   L=1.05m  M=1.116kNm  S=1.162MPa  d_LL=0.05mm/2.917mm  ok
  D6-E6    100x240   L=3.5m  M=8.606kNm  S=8.964MPa  d_LL=4.24mm/9.722mm  ok
  E1-E2    100x240   L=1.5m  M=2.741kNm  S=2.855MPa  d_LL=0.25mm/4.167mm  ok
  E2-E4    100x240   L=1.7m  M=3.52kNm  S=3.667MPa  d_LL=0.413mm/4.722mm  ok
  E2-G2    120x300   L=3.8m  M=10.252kNm  S=5.696MPa  d_LL=2.514mm/10.556mm  ok
  E4-E6    100x240   L=3.05m  M=11.332kNm  S=11.804MPa  d_LL=4.279mm/8.472mm  ok
  E4-F4    100x240   L=3.5m  M=8.606kNm  S=8.964MPa  d_LL=4.24mm/9.722mm  ok
  E6-E7    100x240   L=1.05m  M=1.343kNm  S=1.399MPa  d_LL=0.06mm/2.917mm  ok
  E7-F7    100x240   L=3.5m  M=8.606kNm  S=8.964MPa  d_LL=4.24mm/9.722mm  ok
  F4-F7    120x300   L=4.1m  M=11.935kNm  S=6.631MPa  d_LL=3.407mm/11.389mm  ok
  F4-G4    100x240   L=0.3m  M=0.063kNm  S=0.066MPa  d_LL=0.0mm/0.833mm  ok
  G2-G4    100x240   L=1.7m  M=2.03kNm  S=2.115MPa  d_LL=0.236mm/4.722mm  ok
  D2-D3    120x300   L=4.0m  M=16.31kNm  S=9.061MPa  d_LL=4.475mm/11.111mm  ok

COLUMNS:
  A3       100x100   H=3.5m  P=7.66kN  S=0.7655MPa  SF=16.61  ok
  A5       100x100   H=3.5m  P=13.6kN  S=1.3595MPa  SF=9.35  ok
  B1       100x100   H=3.5m  P=7.39kN  S=0.7394MPa  SF=17.19  ok
  B3       100x100   H=3.5m  P=8.36kN  S=0.8356MPa  SF=15.21  ok
  C5       100x100   H=3.5m  P=11.08kN  S=1.1079MPa  SF=11.48  ok
  C7       100x100   H=3.5m  P=5.67kN  S=0.5675MPa  SF=22.4  ok
  D1       100x100   H=3.5m  P=12.14kN  S=1.2138MPa  SF=10.47  ok
  D2       100x100   H=3.5m  P=14.13kN  S=1.4131MPa  SF=9.0  ok
  D5       100x100   H=3.5m  P=24.5kN  S=2.4499MPa  SF=5.19  ok
  D6       100x100   H=3.5m  P=14.53kN  S=1.453MPa  SF=8.75  ok
  D7       100x100   H=3.5m  P=8.55kN  S=0.8549MPa  SF=14.87  ok
  E1       100x100   H=3.5m  P=14.61kN  S=1.4612MPa  SF=8.7  ok
  E2       100x100   H=3.5m  P=17.02kN  S=1.7019MPa  SF=7.47  ok
  E4       100x100   H=3.5m  P=36.27kN  S=3.6269MPa  SF=3.51  ok
  E6       100x100   H=3.5m  P=17.5kN  S=1.75MPa  SF=7.26  ok
  E7       100x100   H=3.5m  P=10.28kN  S=1.0281MPa  SF=12.37  ok
  F4       100x100   H=3.5m  P=19.77kN  S=1.9769MPa  SF=6.43  ok
  F7       100x100   H=3.5m  P=5.67kN  S=0.5675MPa  SF=22.4  ok
  G2       100x100   H=3.5m  P=5.67kN  S=0.5675MPa  SF=22.4  ok
  G4       100x100   H=3.5m  P=5.67kN  S=0.5675MPa  SF=22.4  ok
```

## Change Summary

The intervention did not alter the building’s structure; all existing elements remain in place. This means there is no change to safety or adaptability, and the overall cost stays within the moderate range of EUR 8,152 (EUR 5,706–12,228). No further action is required.

## Cost & Flexibility Analysis

| Metric | Value |
|--------|-------|
| **Total Structure Build Cost** | **Moderate (EUR 8,152 / 5,706–12,228)** |
| ↳ Volume | 2.405 m³ TIMBER |
| ↳ PEM (works budget) | EUR 5,891 |


> Full structure: Moderate (EUR 8,152 / 5,706–12,228)
