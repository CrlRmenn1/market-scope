# MarketScope scoring engine (version 2.0)

How a scan becomes a score, where each rule comes from, and what is still provisional. Every number here lives in [`constants/engine.py`](../marketscope-backend/constants/engine.py).

Each rule is marked:

- **[study]**: taken from the reference study.
- **[source]**: taken from another cited source.
- **[ours]**: our own calibration for Panabo. Not from a published source, so be ready to defend it.

## Reference study

Carrido, A. J. D. C., Amba, G. W. E., Guevara, C. H., & Claridades, A. R. C. (2026). Central Business District Likeliness Determination Using GIS, Volunteered Geographic Information, and Analytic Hierarchy Process: The Case of Quezon City, Philippines. *ISPRS Annals of the Photogrammetry, Remote Sensing and Spatial Information Sciences*, X-5/W4-2025, 127-134. https://doi.org/10.5194/isprs-annals-X-5-W4-2025-127-2026

It is a Philippine study using the same method: OpenStreetMap roads and POIs, AHP weights, and a weighted overlay.

**Limits of using it here.** It measures how CBD-like an area is in a large metro city, not MSME viability in Panabo. We adopt its method and distance bands, **not its weights**. It also uses population and building-height layers that MarketScope doesn't have.

Other sources:

- İnceyavuz, Alkan & Durduran (2022), shopping centre siting with GIS and AHP in Adana. https://doi.org/10.35414/akufemubid.1099852
- Roig-Tierno et al. (2013), retail site location with GIS and AHP, *Applied Geography* 40, 191-198 (abstract read only). https://doi.org/10.1016/j.apgeog.2013.03.005
- LaLonde (1961), Index of Retail Saturation, as described by secondary sources such as Finch & Broka. Check the original before citing it directly.

## The formula

```
market    = w_competition·C' + w_road·R + w_anchor·A + w_building·B     (each 0-25)
potential = 4 × (w_hazard·H + w_market·market)                          (0-100)
viability = potential × Z                                               (Z = 0 if zoning bans the business, else 1)
```

Rounding happens only at the end, so each factor's points add up to the score (`score_explanation` in the scan result). If a factor's data couldn't be loaded, it is left out and the remaining weights are rescaled. The report says so; it never fills in a stand-in score.

## Factors

All distances are straight-line and fixed per criterion. The scan radius only decides which competitors the map lists, so the same pin and business always get the same score. The study uses 3-step classes; we interpolate between its breakpoints **[ours]**, because a step lets a one-metre move jump a whole class.

### Zoning: a constraint, not a factor

A zone either allows the business or it doesn't (`zoning_allowed_uses`, edited by the admin). As a weighted factor it gave every allowed site the same 30 free points and let a banned site reach 70. A constraint is the usual GIS-MCDA treatment of a legal rule **[ours: confirm a citation before using this as a claim]**.

| Situation | State | Effect |
|---|---|---|
| Allowed in the zone | permitted | None |
| Not allowed in the zone | not permitted | Score 0, verdict Not Permitted, potential still shown |
| No layer, or outside every zone | unverified | Scored, but can't be Highly Suitable, and the report says to confirm with the CPDO |

### Flood hazard (H)

None 25, Moderate 18, High 12, Very High 5, from the active hazard layer. A Very High site can't be labelled Highly Suitable **[ours]**. With no hazard layer the factor is left out; the site is not called safe.

### Road access (R)

`R = 25 × (0.6·A + 0.4·F)`. The 60/40 split is **[ours]**.

| Part | What it measures | Full value to | Half value at | Zero at |
|---|---|---|---|---|
| A | Best major road in range | 250 m **[study]** | 500 m **[study]** | 1000 m **[ours]** |
| F | Best road at the site | 30 m **[ours]** | 100 m **[ours]** | 300 m **[ours]** |

Each is multiplied by a class value **[ours]**: motorway, trunk or primary 1.0; secondary 0.95; tertiary 0.85; unclassified 0.7; residential or living street 0.6; service 0.4; pedestrian 0.3; track 0.2. Footways, paths and cycleways don't count. The study's major roads are trunk and primary **[study]**; Panabo has only 2 primary segments, so secondary and tertiary also count **[ours]**.

Both parts take the *best* road in range, never simply the nearest one.

### Anchors (A)

`A = 25 × (1 − e^(−Σ power·m(d) / T))`, where T is the business type's target power × 2.5 **[ours]**. Extra anchors add less and less, so a busy area can't exceed the maximum.

| Category | Full value to | Half value at | Source |
|---|---|---|---|
| Transport terminal | 400 m | 800 m | **[study]** |
| Market, mall/commercial, bank, government | 400 m | 800 m | **[study]** |
| Hospital/healthcare | 300 m | 600 m | **[study]** |
| Park/recreation | 500 m | 1000 m | **[study]** |
| School | 400 m | 800 m | **[ours]**: the study's survey dropped education, but schools matter to MSMEs |

Each fades to zero at 1.5× its half-value distance **[ours]**, so there is no cut-off at an edge.

**Sources, merged for every scan** ([`services/anchors.py`](../marketscope-backend/services/anchors.py)):

1. Anchors added on the admin Anchors page.
2. The 8 original anchors, copied once into the same table so they can be edited.
3. OpenStreetMap places (`OSM_ANCHOR_TAGS`). Tag families follow the study's use of OSM POIs **[study]**; powers are **[ours]**. ATMs, places of worship and unnamed places are excluded **[ours]**.

An admin can correct or hide an OSM anchor. An OSM anchor within 100 m of a curated one of the same category counts as the same place **[ours]**.

### Competition (C and C')

`C = 25 − 7·ln(1 + pressure × sensitivity)`, where each known competitor within 800 m **[study: the commercial outer band]** adds `1 − d/800`. A verified shop counts the same as an OSM one: one shop is one shop. Same-name entries within 30 m are one shop **[ours]**.

**The demand check.** `C' = C × D`, where D (0-1) is the weighted average of the anchor and building scores **[ours]**.

The approved design used C directly. Validating it showed why that fails: a bare field with no road, anchor or building scored 57, and a rural spot outranked Gaisano Grand, because "no competitors" earned full points even where there are no customers. Average scores were also higher outside commercial zones than inside. The idea of judging supply against demand comes from the Index of Retail Saturation **[source]**, which normally uses household and spending data. MarketScope has neither, so anchors and buildings stand in for demand.

The report shows how crowded the area is, and says when low demand reduced how much that counted.

Only competitors on OpenStreetMap or added by the admin can be counted, so low competition can mean a gap in the data.

### Building density (B)

`B = 8.5·ln(1 + 0.05 × intensity)`, summed over mapped buildings and land uses within 400 m, fading evenly with distance, with a small bonus for larger footprints **[ours]**. It is a rough stand-in for nearby activity, not a head count.

## Weights

Saved in `ahp_weight_configs` and shown in reports. A matrix is only used if it has the expected criteria and CR < 0.10.

**Current weights are provisional, set by the project team, not expert answers.** `hazard : market` is 1:3 (0.25 / 0.75). Market weights round the app's earlier per-business weights to the nearest 1-9 Saaty judgment. Rounding makes several business types share the same weights, which only real answers can separate.

To replace them, collect answers in the format of the expert questionnaire, then:

```
python scripts/import_ahp_judgments.py answers.csv            # shows the result
python scripts/import_ahp_judgments.py answers.csv --apply    # saves it
```

As in the study, respondents with CR ≥ 0.10 are left out **[study]**, the rest are combined by geometric mean, and a leave-one-out check shows how far any one person moves the result **[study]**. Restart the backend, then re-run calibration.

## Verdict

| Score | Verdict |
|---|---|
| 68 and above | Highly Suitable |
| 47 to 67 | Moderately Suitable |
| Below 47 | Low Suitability |
| Zoning bans it | Not Permitted |

The cut-offs are the Jenks natural breaks of citywide scores **[study: same classification method]**, from `scripts/calibrate_engine.py` (437 grid points, 13 business types, provisional weights). **Re-run it after importing expert weights**, since new weights can move them. Every page takes its label from the backend ([`services/verdict.py`](../marketscope-backend/services/verdict.py)).

## Validation

Measured with `scripts/calibrate_engine.py` and the test suite.

| Check | Old engine | Engine 2.0 |
|---|---|---|
| Moving a pin 25 m changes road by 5+ (154 commercial points) | 36% of points | 0% |
| Moving a pin 25 m changes road by 10+ | 28% of points | 0% |
| Changing the map radius changes the score | Yes (78→88 at one pin) | Never |
| Empty land, coffee | 46 | 25 |
| Kiosk, share of city grid labelled high | 95% at 70+ | 25% Highly Suitable |

Coffee, same pin:

| Site | Old | New |
|---|---|---|
| Integrated Bus and Jeepney Terminal | 90 | 89 |
| Panabo City Market | 90 | 86 |
| Panabo Public Market | 80 | 72 |
| Gaisano Grand Panabo | 76 | 68 |
| Rural northeast | 52 | 46 |
| Empty land east | 46 | 25 |

Moving a pin 25 m still changes the *total* by 5 or more at 12.3% of points, nearly all where it crosses a flood-zone edge, which is a real change in hazard class (0.6% away from those edges).

Average market potential is 58.5 inside commercial zones and 55.0 outside. That is the right direction but a small gap, partly because residential land near downtown also scores well on market factors; it's banned for many businesses by zoning, not by this number.

**What this does not show.** These checks show the engine is stable and ranks clear cases sensibly. They don't show that a high score predicts business success. That needs outcome data, which the capstone evaluation tests on another city.

## Business trend suggestions

The Trends page reverses the search: instead of scoring a site for a chosen business, it asks which businesses fit an area. It adds no weights and changes no scores. It groups and orders saved engine results ([`services/trend_suggestions.py`](../marketscope-backend/services/trend_suggestions.py)). All the thresholds below are **[ours]**, in `constants/engine.py`.

- **Area.** A spot belongs to its nearest named place in `panabo.pbf` (OSM `place` = suburb, quarter or village). The file has no barangay polygons, so an area is "around Gredu", not a legal boundary, and some named places aren't barangays.
- **Area score.** The average of a business's best 3 permitted spots in the area, so one lucky point doesn't decide it. Spots where zoning bans the business are left out.
- **Suggestion.** An area score in the Highly Suitable class, unless a flood or zoning cap on the best spot lowers its verdict.
- **Competitor data.** Fewer than 6 known competitors citywide counts as thin data, because "no competition" more likely means the shops aren't on record. These businesses rank below the others and carry a warning. The cut-off comes from the counts on 2026-11-06: barber 2, meat 3 and hardware 5 fall under it, the rest have 6 to 25. Reaching it doesn't prove a list is complete.
- **Possible market gap.** At most 1 competitor within 800 m of the best spot, demand share of at least 0.6 (about the top 30% of scanned spots), and enough competitor data. It is a prompt to check in person, not a finding.

**What this does not show.** This is a snapshot of current conditions. It doesn't measure growth or decline, because there is no historical data, and it doesn't predict success. Scores across business types are only as comparable as their competitor records.

## Known limits

- Distances are straight-line. The study recommends real travel paths as future work, and the same applies here.
- No population or spending data. Anchors and buildings stand in for demand.
- Results depend on OpenStreetMap coverage, and on the admin keeping anchors and competitors current.
- The zoning layer deliberately covers the center of Panabo City, which is the project's scope. Sites outside it are unverified: they still get a score, but can't be Highly Suitable, so results there are less reliable. If a site looks wrongly banned, check its zone and the allowed-uses table first, since zoning is a hard constraint.
- Many provisional values are **[ours]**, and all are in one file so they can be reviewed and changed.

## Changing the engine

Change `constants/engine.py`, then:

1. Run `python -m unittest discover tests` and `python scripts/calibrate_engine.py`.
2. Raise `ENGINE_VERSION` if scores change, so saved trend scans get redone and older scans are labelled.
3. Add known good and bad sites to `tests/fixtures/engine_benchmark.json`; the tests check their ranking.
4. If the capstone evaluation is still in use, re-run its `tools/parity_check.py`.
