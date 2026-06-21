# Structural Evaluation Report

**Date:** 2026-06-21 11:35:26
**Prompt:** what if we remove column E4

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
  A5-A8    100x240   L=3.5m  M=5.543kNm  S=5.774MPa  d_LL=4.24mm/9.722mm  ok
  A5-B5    100x240   L=0.55m  M=0.137kNm  S=0.143MPa  d_LL=0.003mm/1.528mm  ok
  A8-D8    100x240   L=3.5m  M=5.543kNm  S=5.774MPa  d_LL=4.24mm/9.722mm  ok
  B4-B5    100x240   L=2.0m  M=1.81kNm  S=1.885MPa  d_LL=0.452mm/5.556mm  ok
  B4-C4    100x240   L=0.45m  M=0.092kNm  S=0.095MPa  d_LL=0.001mm/1.25mm  ok
  B5-D5    100x240   L=2.95m  M=3.938kNm  S=4.102MPa  d_LL=2.14mm/8.194mm  ok
  C1-C4    120x300   L=4.5m  M=9.315kNm  S=5.175MPa  d_LL=4.944mm/12.5mm  ok
  C1-E1    100x240   L=3.8m  M=6.85kNm  S=7.135MPa  d_LL=6.187mm/10.556mm  ok
  C4-D4    100x240   L=2.5m  M=2.828kNm  S=2.946MPa  d_LL=1.104mm/6.944mm  ok
  D4-D5    100x240   L=2.0m  M=1.81kNm  S=1.885MPa  d_LL=0.452mm/5.556mm  ok
  D5-D6    100x240   L=0.5m  M=0.113kNm  S=0.118MPa  d_LL=0.002mm/1.389mm  ok
  D6-D7    100x240   L=1.25m  M=0.707kNm  S=0.736MPa  d_LL=0.069mm/3.472mm  ok
  D6-E6    100x240   L=1.3m  M=0.765kNm  S=0.797MPa  d_LL=0.081mm/3.611mm  ok
  D7-D8    100x240   L=1.75m  M=1.386kNm  S=1.444MPa  d_LL=0.265mm/4.861mm  ok
  D7-E7    100x240   L=1.3m  M=0.765kNm  S=0.797MPa  d_LL=0.081mm/3.611mm  ok
  E1-E2    100x240   L=2.1m  M=1.996kNm  S=2.079MPa  d_LL=0.55mm/5.833mm  ok
  E2-F2    100x240   L=2.6m  M=3.059kNm  S=3.186MPa  d_LL=1.291mm/7.222mm  ok
  E6-F6    100x240   L=2.6m  M=3.059kNm  S=3.186MPa  d_LL=1.291mm/7.222mm  ok
  E7-E8    100x240   L=1.75m  M=1.386kNm  S=1.444MPa  d_LL=0.265mm/4.861mm  ok
  E7-F7    100x240   L=2.6m  M=3.059kNm  S=3.186MPa  d_LL=1.291mm/7.222mm  ok
  E8-F8    100x240   L=2.6m  M=3.059kNm  S=3.186MPa  d_LL=1.291mm/7.222mm  ok
  F2-F3    100x240   L=0.75m  M=0.405kNm  S=0.422MPa  d_LL=0.014mm/2.083mm  ok
  F3-F4    100x240   L=1.65m  M=1.961kNm  S=2.043MPa  d_LL=0.338mm/4.583mm  ok
  F3-G3    100x240   L=3.85m  M=6.707kNm  S=6.987MPa  d_LL=6.208mm/10.694mm  ok
  F4-F5    100x240   L=2.0m  M=2.882kNm  S=3.002MPa  d_LL=0.729mm/5.556mm  ok
  F5-F6    100x240   L=0.5m  M=0.18kNm  S=0.188MPa  d_LL=0.003mm/1.389mm  ok
  F5-G5    100x240   L=3.85m  M=6.707kNm  S=6.987MPa  d_LL=6.208mm/10.694mm  ok
  F6-F7    100x240   L=1.25m  M=1.126kNm  S=1.173MPa  d_LL=0.111mm/3.472mm  ok
  F7-F8    100x240   L=1.75m  M=2.206kNm  S=2.298MPa  d_LL=0.427mm/4.861mm  ok
  F8-G8    100x240   L=3.85m  M=6.707kNm  S=6.987MPa  d_LL=6.208mm/10.694mm  ok
  G3-I3    100x240   L=3.9m  M=6.883kNm  S=7.169MPa  d_LL=6.537mm/10.833mm  ok
  G5-G7    100x240   L=1.75m  M=2.19kNm  S=2.281MPa  d_LL=0.424mm/4.861mm  ok
  G5-I5    100x240   L=3.9m  M=6.883kNm  S=7.169MPa  d_LL=6.537mm/10.833mm  ok
  G7-G8    100x240   L=1.75m  M=2.19kNm  S=2.281MPa  d_LL=0.424mm/4.861mm  ok
  G7-H7    100x240   L=2.55m  M=2.942kNm  S=3.065MPa  d_LL=1.195mm/7.083mm  ok
  G8-H8    100x240   L=2.55m  M=2.942kNm  S=3.065MPa  d_LL=1.195mm/7.083mm  ok
  H7-H8    100x240   L=1.75m  M=1.386kNm  S=1.444MPa  d_LL=0.265mm/4.861mm  ok
  H7-I7    100x240   L=1.35m  M=0.825kNm  S=0.859MPa  d_LL=0.094mm/3.75mm  ok
  I3-I5    100x240   L=3.65m  M=6.028kNm  S=6.28MPa  d_LL=5.015mm/10.139mm  ok
  I5-I7    100x240   L=1.75m  M=1.386kNm  S=1.444MPa  d_LL=0.265mm/4.861mm  ok
  G3-G4    150x360   L=3.65m  M=28.319kNm  S=8.74MPa  d_LL=3.98mm/10.139mm  ok
  D4-E4    120x300   L=3.9m  M=17.165kNm  S=9.536MPa  d_LL=5.892mm/10.833mm  ok
  E2-E4    150x360   L=4.9m  M=26.775kNm  S=8.264MPa  d_LL=6.735mm/13.611mm  ok
  A5-A8    100x240   L=3.5m  M=5.543kNm  S=5.774MPa  d_LL=4.24mm/9.722mm  ok
  A5-B5    100x240   L=0.55m  M=0.137kNm  S=0.143MPa  d_LL=0.003mm/1.528mm  ok
  A8-D8    100x240   L=3.5m  M=5.543kNm  S=5.774MPa  d_LL=4.24mm/9.722mm  ok
  B4-B5    100x240   L=2.0m  M=1.81kNm  S=1.885MPa  d_LL=0.452mm/5.556mm  ok
  B4-C4    100x240   L=0.45m  M=0.092kNm  S=0.095MPa  d_LL=0.001mm/1.25mm  ok
  B5-D5    100x240   L=2.95m  M=3.938kNm  S=4.102MPa  d_LL=2.14mm/8.194mm  ok
  C1-C4    120x300   L=4.5m  M=9.315kNm  S=5.175MPa  d_LL=4.944mm/12.5mm  ok
  C1-E1    100x240   L=3.8m  M=6.85kNm  S=7.135MPa  d_LL=6.187mm/10.556mm  ok
  C4-D4    100x240   L=2.5m  M=2.828kNm  S=2.946MPa  d_LL=1.104mm/6.944mm  ok
  D4-D5    100x240   L=2.0m  M=1.81kNm  S=1.885MPa  d_LL=0.452mm/5.556mm  ok
  D4-E4    120x300   L=1.3m  M=0.777kNm  S=0.432MPa  d_LL=0.034mm/3.611mm  ok
  D7-D8    100x240   L=1.75m  M=1.386kNm  S=1.444MPa  d_LL=0.265mm/4.861mm  ok
  D7-E7    100x240   L=1.3m  M=0.765kNm  S=0.797MPa  d_LL=0.081mm/3.611mm  ok
  E1-E2    100x240   L=2.1m  M=1.996kNm  S=2.079MPa  d_LL=0.55mm/5.833mm  ok
  E2-E4    150x360   L=2.4m  M=2.714kNm  S=0.838MPa  d_LL=0.185mm/6.667mm  ok
  E2-F2    100x240   L=2.6m  M=3.059kNm  S=3.186MPa  d_LL=1.291mm/7.222mm  ok
  E4-E6    100x240   L=2.5m  M=2.828kNm  S=2.946MPa  d_LL=1.104mm/6.944mm  ok
  E4-F4    100x240   L=2.6m  M=3.059kNm  S=3.186MPa  d_LL=1.291mm/7.222mm  ok
  E6-F6    100x240   L=2.6m  M=3.059kNm  S=3.186MPa  d_LL=1.291mm/7.222mm  ok
  E7-E8    100x240   L=1.75m  M=1.386kNm  S=1.444MPa  d_LL=0.265mm/4.861mm  ok
  E7-F7    100x240   L=2.6m  M=3.059kNm  S=3.186MPa  d_LL=1.291mm/7.222mm  ok
  E8-F8    100x240   L=2.6m  M=3.059kNm  S=3.186MPa  d_LL=1.291mm/7.222mm  ok
  F2-F3    100x240   L=0.75m  M=0.405kNm  S=0.422MPa  d_LL=0.014mm/2.083mm  ok
  F3-F4    100x240   L=1.65m  M=1.961kNm  S=2.043MPa  d_LL=0.338mm/4.583mm  ok
  F3-G3    100x240   L=3.85m  M=6.707kNm  S=6.987MPa  d_LL=6.208mm/10.694mm  ok
  F4-F5    100x240   L=2.0m  M=2.882kNm  S=3.002MPa  d_LL=0.729mm/5.556mm  ok
  F4-G4    100x240   L=3.85m  M=6.707kNm  S=6.987MPa  d_LL=6.208mm/10.694mm  ok
  F5-F6    100x240   L=0.5m  M=0.18kNm  S=0.188MPa  d_LL=0.003mm/1.389mm  ok
  F5-G5    100x240   L=3.85m  M=6.707kNm  S=6.987MPa  d_LL=6.208mm/10.694mm  ok
  F6-F7    100x240   L=1.25m  M=1.126kNm  S=1.173MPa  d_LL=0.111mm/3.472mm  ok
  F7-F8    100x240   L=1.75m  M=2.206kNm  S=2.298MPa  d_LL=0.427mm/4.861mm  ok
  F8-G8    100x240   L=3.85m  M=6.707kNm  S=6.987MPa  d_LL=6.208mm/10.694mm  ok
  G3-G4    150x360   L=1.65m  M=1.998kNm  S=0.617MPa  d_LL=0.066mm/4.583mm  ok
  G3-I3    100x240   L=3.9m  M=6.883kNm  S=7.169MPa  d_LL=6.537mm/10.833mm  ok
  G4-G5    100x240   L=2.0m  M=2.86kNm  S=2.979MPa  d_LL=0.723mm/5.556mm  ok
  G5-G7    100x240   L=1.75m  M=2.19kNm  S=2.281MPa  d_LL=0.424mm/4.861mm  ok
  G5-I5    100x240   L=3.9m  M=6.883kNm  S=7.169MPa  d_LL=6.537mm/10.833mm  ok
  G7-G8    100x240   L=1.75m  M=2.19kNm  S=2.281MPa  d_LL=0.424mm/4.861mm  ok
  G7-H7    100x240   L=2.55m  M=2.942kNm  S=3.065MPa  d_LL=1.195mm/7.083mm  ok
  G8-H8    100x240   L=2.55m  M=2.942kNm  S=3.065MPa  d_LL=1.195mm/7.083mm  ok
  H7-H8    100x240   L=1.75m  M=1.386kNm  S=1.444MPa  d_LL=0.265mm/4.861mm  ok
  H7-I7    100x240   L=1.35m  M=0.825kNm  S=0.859MPa  d_LL=0.094mm/3.75mm  ok
  I3-I5    100x240   L=3.65m  M=6.028kNm  S=6.28MPa  d_LL=5.015mm/10.139mm  ok
  I5-I7    100x240   L=1.75m  M=1.386kNm  S=1.444MPa  d_LL=0.265mm/4.861mm  ok

COLUMNS:
  A5       100x100   H=3.5m  P=7.35kN  S=0.735MPa  SF=17.3  ok
  A8       100x100   H=3.5m  P=7.35kN  S=0.735MPa  SF=17.3  ok
  B4       100x100   H=3.5m  P=7.35kN  S=0.735MPa  SF=17.3  ok
  B5       100x100   H=3.5m  P=7.35kN  S=0.735MPa  SF=17.3  ok
  C1       100x100   H=3.5m  P=11.19kN  S=1.1191MPa  SF=11.36  ok
  C4       100x100   H=3.5m  P=19.19kN  S=1.9193MPa  SF=6.62  ok
  D4       100x100   H=3.5m  P=24.62kN  S=2.4622MPa  SF=5.16  ok
  D5       100x100   H=3.5m  P=16.98kN  S=1.6975MPa  SF=7.49  ok
  D7       100x100   H=3.5m  P=20.3kN  S=2.03MPa  SF=6.26  ok
  D8       100x100   H=3.5m  P=11.99kN  S=1.1987MPa  SF=10.61  ok
  E1       100x100   H=3.5m  P=14.68kN  S=1.4682MPa  SF=8.66  ok
  E2       100x100   H=3.5m  P=19.8kN  S=1.9801MPa  SF=6.42  ok
  E6       100x100   H=3.5m  P=12.29kN  S=1.2294MPa  SF=10.34  ok
  E7       100x100   H=3.5m  P=20.82kN  S=2.0825MPa  SF=6.1  ok
  E8       100x100   H=3.5m  P=12.29kN  S=1.2294MPa  SF=10.34  ok
  F2       100x100   H=3.5m  P=32.52kN  S=3.2519MPa  SF=3.91  ok
  F3       100x100   H=3.5m  P=27.44kN  S=2.744MPa  SF=4.63  ok
  F4       100x100   H=3.5m  P=41.55kN  S=4.1549MPa  SF=3.06  ok
  F5       100x100   H=3.5m  P=28.57kN  S=2.8569MPa  SF=4.45  ok
  F6       100x100   H=3.5m  P=20.1kN  S=2.0103MPa  SF=6.32  ok
  F7       100x100   H=3.5m  P=34.21kN  S=3.4212MPa  SF=3.72  ok
  F8       100x100   H=3.5m  P=20.1kN  S=2.0103MPa  SF=6.32  ok
  G3       100x100   H=3.5m  P=27.23kN  S=2.723MPa  SF=4.67  ok
  G5       100x100   H=3.5m  P=28.35kN  S=2.835MPa  SF=4.48  ok
  G7       100x100   H=3.5m  P=33.95kN  S=3.395MPa  SF=3.74  ok
  G8       100x100   H=3.5m  P=19.95kN  S=1.995MPa  SF=6.37  ok
  H7       100x100   H=3.5m  P=20.83kN  S=2.0825MPa  SF=6.1  ok
  H8       100x100   H=3.5m  P=12.29kN  S=1.2294MPa  SF=10.34  ok
  I3       100x100   H=3.5m  P=7.35kN  S=0.735MPa  SF=17.3  ok
  I5       100x100   H=3.5m  P=7.35kN  S=0.735MPa  SF=17.3  ok
  I7       100x100   H=3.5m  P=7.44kN  S=0.7437MPa  SF=17.09  ok
  A5       100x100   H=3.5m  P=3.67kN  S=0.3675MPa  SF=34.59  ok
  A8       100x100   H=3.5m  P=3.67kN  S=0.3675MPa  SF=34.59  ok
  B4       100x100   H=3.5m  P=3.67kN  S=0.3675MPa  SF=34.59  ok
  B5       100x100   H=3.5m  P=3.67kN  S=0.3675MPa  SF=34.59  ok
  C1       100x100   H=3.5m  P=5.6kN  S=0.5596MPa  SF=22.72  ok
  C4       100x100   H=3.5m  P=9.6kN  S=0.9597MPa  SF=13.25  ok
  D4       100x100   H=3.5m  P=12.31kN  S=1.2311MPa  SF=10.33  ok
  D5       100x100   H=3.5m  P=8.49kN  S=0.8487MPa  SF=14.98  ok
  D7       100x100   H=3.5m  P=10.15kN  S=1.015MPa  SF=12.53  ok
  D8       100x100   H=3.5m  P=5.99kN  S=0.5994MPa  SF=21.21  ok
  E1       100x100   H=3.5m  P=7.34kN  S=0.7341MPa  SF=17.32  ok
  E2       100x100   H=3.5m  P=9.9kN  S=0.9901MPa  SF=12.84  ok
  E4       100x100   H=3.5m  P=12.63kN  S=1.2631MPa  SF=10.07  ok
  E6       100x100   H=3.5m  P=6.15kN  S=0.6147MPa  SF=20.68  ok
  E7       100x100   H=3.5m  P=10.41kN  S=1.0412MPa  SF=12.21  ok
  E8       100x100   H=3.5m  P=6.15kN  S=0.6147MPa  SF=20.68  ok
  F2       100x100   H=3.5m  P=16.26kN  S=1.626MPa  SF=7.82  ok
  F3       100x100   H=3.5m  P=13.72kN  S=1.372MPa  SF=9.27  ok
  F4       100x100   H=3.5m  P=20.77kN  S=2.0775MPa  SF=6.12  ok
  F5       100x100   H=3.5m  P=14.28kN  S=1.4284MPa  SF=8.9  ok
  F6       100x100   H=3.5m  P=10.05kN  S=1.0052MPa  SF=12.65  ok
  F7       100x100   H=3.5m  P=17.11kN  S=1.7106MPa  SF=7.43  ok
  F8       100x100   H=3.5m  P=10.05kN  S=1.0052MPa  SF=12.65  ok
  G3       100x100   H=3.5m  P=13.62kN  S=1.3615MPa  SF=9.34  ok
  G4       100x100   H=3.5m  P=20.61kN  S=2.0615MPa  SF=6.17  ok
  G5       100x100   H=3.5m  P=14.18kN  S=1.4175MPa  SF=8.97  ok
  G7       100x100   H=3.5m  P=16.98kN  S=1.6975MPa  SF=7.49  ok
  G8       100x100   H=3.5m  P=9.98kN  S=0.9975MPa  SF=12.74  ok
  H7       100x100   H=3.5m  P=10.41kN  S=1.0413MPa  SF=12.21  ok
  H8       100x100   H=3.5m  P=6.15kN  S=0.6147MPa  SF=20.68  ok
  I3       100x100   H=3.5m  P=3.67kN  S=0.3675MPa  SF=34.59  ok
  I5       100x100   H=3.5m  P=3.67kN  S=0.3675MPa  SF=34.59  ok
  I7       100x100   H=3.5m  P=3.72kN  S=0.3719MPa  SF=34.19  ok
```

## Change Summary

The upgrade of the two 100 × 240 mm beams to larger sections – one to 120 × 300 mm and the other to 150 × 360 mm – increases the structural capacity while keeping the overall build cost modest. The change is reflected in a low financial impact (EUR 3,877 total for the intervention) and a short administrative burden of 14 weeks, with high adaptability confidence. This move improves safety margins without significantly raising costs, and it keeps the design flexible for future alterations.

Trade‑offs: Safety vs cost – the larger sections give a higher safety margin at a modest additional expense.

Next step: re‑run the evaluation to confirm the change holds.

## Cost & Flexibility Analysis

| Metric | Value |
|--------|-------|
| **Total Structure Build Cost** | **Moderate (EUR 23,596 / 16,517–35,394)** |
| ↳ Volume | 7.747 m³ TIMBER |
| ↳ PEM (works budget) | EUR 18,980 |
| Last Modification Cost | Low (EUR 3,877) |
| ↳ Intervention | EUR 3,160 (labour, demolition, material) |
| ↳ Overhead | EUR 717 (mobilisation, temp works, fees) |
| Cost Driver | Component B — Labour |
| Admin Burden | Low |
| Admin Critical Path | 14 wks (mid) |
| Dominant Process | P2 — Municipal Building Permit |
| Adaptability | High (MEDIUM confidence) |
| Adaptability Constraint | Regulatory Footprint |
| Decision Signal | efficient_and_adaptable |

> Full structure: Moderate (EUR 23,596) | 2 changed | Cost: Low (EUR 3,877 total / 3,160 intervention / 717 overhead) | Admin: Low (14 wks mid) | Adaptability: High (MEDIUM confidence) | Signal: efficient_and_adaptable
