# SolarScope web demo

This is a front-end-only demo of the SolarScope dashboard, for showing the flow to the group. There is no back-end: every number comes from `src/data.ts`.

Live: https://solarscope-demo.vercel.app

## Run locally

```bash
npm install
npm run dev
```

## What is real and what is a placeholder

| | Figures | Source |
|---|---|---|
| Real | 420,904 readings, 1,424 repeat readings, 99% usable, H02 clock (1,351 readings), H09 sensor (since Jan 19), H11 offline (44.5 h), 8 truck rolls / $2,800, P22 repair history | MVP 1 test data, `docs/data_profile.md` and the data-quality run |
| Placeholder | P22 / P08 / P33 faults, kWh lost, 48,212 kWh made, work orders D001–D003 | The analysis stages are not built yet |

The "Download PDF" buttons show a notice, because the PDFs come from the pipeline. The CSV downloads contain demo data.

## Design

The screens follow the Figma page "App · Redesign v2" (Round 3). The roof in `src/Roof.tsx` uses the same isometric geometry as the Figma frames, a 1440 × 960 canvas, so the two line up exactly.

## Deploy

```bash
npx vercel deploy --prod
```
