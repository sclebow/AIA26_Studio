# Structural Evaluation Report

**Date:** 2026-05-30 06:02:41
**Prompt:** find minimum steel sections

## Analysis Parameters

| Parameter | Value |
|-----------|-------|
| Material | STEEL |
| Floor build-up (SDL) | 3.5 kN/m² |
| Live load | 2.0 kN/m² |
| Total applied load | 5.5 kN/m² |

## Structural Checks

```
Structural evaluation: PASS

BEAMS:
  A1-A3    IPE240    L=5.0m  M=43.928kNm  S=135.456MPa  d_LL=5.227mm/13.889mm  ok
  A1-B1    IPE240    L=5.0m  M=35.335kNm  S=108.957MPa  d_LL=4.182mm/13.889mm  ok
  A3-A5    IPE240    L=5.0m  M=43.928kNm  S=135.456MPa  d_LL=5.227mm/13.889mm  ok
  A3-B3    IPE200    L=5.0m  M=17.886kNm  S=92.054MPa  d_LL=4.188mm/13.889mm  ok
  A5-B5    IPE200    L=5.0m  M=26.48kNm  S=136.284MPa  d_LL=6.283mm/13.889mm  ok
  B1-B2    IPE200    L=4.0m  M=22.447kNm  S=115.528MPa  d_LL=3.431mm/11.111mm  ok
  B1-C1    IPE160    L=3.0m  M=12.552kNm  S=115.478MPa  d_LL=2.427mm/8.333mm  ok
  B2-B3    IPE120    L=1.0m  M=1.388kNm  S=26.188MPa  d_LL=0.082mm/2.778mm  ok
  B2-C2    IPE120    L=3.0m  M=7.851kNm  S=148.133MPa  d_LL=4.146mm/8.333mm  ok
  B3-B4    IPE120    L=2.0m  M=5.552kNm  S=104.752MPa  d_LL=1.31mm/5.556mm  ok
  B4-B5    IPE160    L=3.0m  M=12.552kNm  S=115.478MPa  d_LL=2.427mm/8.333mm  ok
  B4-C4    IPE120    L=3.0m  M=7.851kNm  S=148.133MPa  d_LL=4.146mm/8.333mm  ok
  B5-C5    IPE160    L=3.0m  M=9.459kNm  S=87.016MPa  d_LL=1.821mm/8.333mm  ok
  C1-C2    IPE200    L=4.0m  M=16.947kNm  S=87.221MPa  d_LL=2.573mm/11.111mm  ok
  C1-E1    IPE300    L=6.0m  M=51.401kNm  S=92.282MPa  d_LL=4.039mm/16.667mm  ok
  C2-C4    IPE160    L=3.0m  M=9.459kNm  S=87.016MPa  d_LL=1.821mm/8.333mm  ok
  C2-D2    IPE120    L=3.0m  M=7.851kNm  S=148.133MPa  d_LL=4.146mm/8.333mm  ok
  C4-C5    IPE160    L=3.0m  M=9.459kNm  S=87.016MPa  d_LL=1.821mm/8.333mm  ok
  C4-D4    IPE120    L=3.0m  M=7.851kNm  S=148.133MPa  d_LL=4.146mm/8.333mm  ok
  C5-E5    IPE240    L=6.0m  M=38.507kNm  S=118.739MPa  d_LL=6.504mm/16.667mm  ok
  D2-D4    IPE160    L=3.0m  M=9.459kNm  S=87.016MPa  d_LL=1.821mm/8.333mm  ok
  D2-E2    IPE120    L=3.0m  M=7.851kNm  S=148.133MPa  d_LL=4.146mm/8.333mm  ok
  D4-E4    IPE120    L=3.0m  M=7.851kNm  S=148.133MPa  d_LL=4.146mm/8.333mm  ok
  E1-E2    IPE200    L=4.0m  M=16.947kNm  S=87.221MPa  d_LL=2.573mm/11.111mm  ok
  E2-E4    IPE160    L=3.0m  M=9.459kNm  S=87.016MPa  d_LL=1.821mm/8.333mm  ok
  E4-E5    IPE160    L=3.0m  M=9.459kNm  S=87.016MPa  d_LL=1.821mm/8.333mm  ok

COLUMNS:
  A1       HSS80x80x5 H=3.5m  P=27.91kN  S=18.8558MPa  SF=18.86  ok
  A3       HSS80x80x5 H=3.5m  P=21.03kN  S=14.2106MPa  SF=25.02  ok
  A5       HSS80x80x5 H=3.5m  P=21.03kN  S=14.2106MPa  SF=25.02  ok
  B1       HSS80x80x5 H=3.5m  P=44.41kN  S=30.0045MPa  SF=11.85  ok
  B2       HSS80x80x5 H=3.5m  P=55.41kN  S=37.4369MPa  SF=9.5  ok
  B3       HSS80x80x5 H=3.5m  P=33.41kN  S=22.572MPa  SF=15.75  ok
  B4       HSS80x80x5 H=3.5m  P=55.41kN  S=37.4369MPa  SF=9.5  ok
  B5       HSS80x80x5 H=3.5m  P=33.41kN  S=22.572MPa  SF=15.75  ok
  C1       HSS80x80x5 H=3.5m  P=33.41kN  S=22.572MPa  SF=15.75  ok
  C2       HSS80x80x5 H=3.5m  P=41.66kN  S=28.1464MPa  SF=12.63  ok
  C4       HSS80x80x5 H=3.5m  P=41.66kN  S=28.1464MPa  SF=12.63  ok
  C5       HSS80x80x5 H=3.5m  P=25.16kN  S=16.9977MPa  SF=20.92  ok
  D2       HSS80x80x5 H=3.5m  P=41.66kN  S=28.1464MPa  SF=12.63  ok
  D4       HSS80x80x5 H=3.5m  P=41.66kN  S=28.1464MPa  SF=12.63  ok
  E1       HSS80x80x5 H=3.5m  P=16.91kN  S=11.4234MPa  SF=31.13  ok
  E2       HSS80x80x5 H=3.5m  P=21.03kN  S=14.2106MPa  SF=25.02  ok
  E4       HSS80x80x5 H=3.5m  P=21.03kN  S=14.2106MPa  SF=25.02  ok
  E5       HSS80x80x5 H=3.5m  P=12.78kN  S=8.6362MPa  SF=41.18  ok
```

## Change Summary

We've successfully upgraded the structural elements to HSS and IPE profiles, improving the design's flexibility while maintaining a low disruption cost of $1,299. This change will allow for more efficient load distribution and potentially reduce future maintenance needs.

## Cost & Flexibility Analysis

| Metric | Value |
|--------|-------|
| Material added | +$1,408 |
| Material saved | -$108 |
| Net cost change | $+1,299 |
| Disruption | Low (2/10) |
| Spatial Penalty | 0.00 |
| Flexibility | 5.0/10 — Moderate |

> 44 upgraded | Added: +$1,408 | Saved: -$108 | Net: $+1,299 | Flexibility: 5.0/10 (Moderate) | Disruption: 2/10 (Low)
