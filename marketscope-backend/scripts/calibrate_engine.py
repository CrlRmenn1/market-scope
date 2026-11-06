"""Measures the scoring engine across Panabo. Reads data only; it changes nothing.

    python scripts/calibrate_engine.py [--step 0.003] [--json out.json]

Reports, per business type: the score distribution and the share in each verdict class.
Citywide: the Jenks natural breaks of all scores (how the Quezon City reference study
classified its map), what each factor's scores look like, and whether scores are
higher inside commercial zones. Plus the pin-stability test: how far scores move when
a pin moves 25 m, on the same 154-point commercial sample as the original measurement.
"""
import argparse
import contextlib
import io
import json
import os
import statistics
import sys
from collections import Counter
from unittest.mock import patch

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_ROOT)
os.chdir(BACKEND_ROOT)

from constants.engine import VERDICT_HIGH_MIN, VERDICT_MODERATE_MIN  # noqa: E402
from constants.geo import PANABO_BOUNDS, ZONING_LAYERS  # noqa: E402
from constants.msme import MSME_CATEGORY_PROFILES  # noqa: E402
from db.queries import fetch_custom_msmes, fetch_verified_local_features  # noqa: E402
from models.requests import AnalysisRequest  # noqa: E402
from services import scoring  # noqa: E402
from services.ahp_weights import _load_ahp_weights_cache  # noqa: E402
from services.analysis import perform_analysis  # noqa: E402
from services.anchors import get_scoring_anchors  # noqa: E402
from services.hazard import preload_hazard_layer_cache  # noqa: E402
from services.zoning import get_zoning_features, preload_zoning_layer_cache  # noqa: E402
from utils.geo_libs import Point  # noqa: E402


FACTORS = ("hazard", "competition_density", "road_access", "anchor_proximity", "building_density")
COMMERCIAL_ZONES = ("general_commercial", "central_business", "commercial")
METERS_PER_DEGREE = 111195.0


def jenks_breaks(scores, classes=3):
    """The class limits that keep the scores within each class most alike (natural
    breaks). Scores are 0-100 integers, so trying every pair of limits is quick."""
    histogram = Counter(scores)

    def within_class_error(low, high):
        members = [(score, count) for score, count in histogram.items() if low <= score < high]
        total = sum(count for _, count in members)
        if not total:
            return 0.0
        mean = sum(score * count for score, count in members) / total
        return sum(count * (score - mean) ** 2 for score, count in members)

    best = None
    for first in range(1, 100):
        for second in range(first + 1, 101):
            error = within_class_error(0, first) + within_class_error(first, second) + within_class_error(second, 101)
            if best is None or error < best[0]:
                best = (error, first, second)
    return best[1], best[2]


def grid_points(step):
    min_lat, max_lat, min_lon, max_lon = PANABO_BOUNDS
    points = []
    lat = min_lat
    while lat <= max_lat:
        lon = min_lon
        while lon <= max_lon:
            points.append((round(lat, 6), round(lon, 6)))
            lon += step
        lat += step
    return points


def commercial_sample():
    """The 154 points of the commercial box, 0.0015 degrees apart."""
    min_lat, max_lat, min_lon, max_lon = ZONING_LAYERS["commercial_proper"]
    points = []
    for lat_index in range(11):
        for lon_index in range(14):
            points.append((round(min_lat + lat_index * 0.0015, 6), round(min_lon + lon_index * 0.0015, 6)))
    return points


class Scanner:
    """Runs the real analysis, reading database records once instead of per scan."""

    def __init__(self):
        self.anchors, _ = get_scoring_anchors()
        self.verified = {
            kind: fetch_verified_local_features(kind) for kind in ("road", "building")
        }
        self.msme_rows = fetch_verified_local_features("msme")
        self.custom = {key: fetch_custom_msmes(key) for key in MSME_CATEGORY_PROFILES}

    def _verified(self, kind, business_type=None, **_):
        if kind == "msme":
            return [row for row in self.msme_rows if row.get("business_type") == business_type]
        return self.verified.get(kind, [])

    @contextlib.contextmanager
    def patched(self):
        def refuse_connection(**_):
            raise RuntimeError("calibration reads each table once, up front")

        with patch.object(scoring.psycopg2, "connect", refuse_connection), \
                patch.object(scoring, "fetch_verified_local_features", self._verified), \
                patch.object(scoring, "fetch_custom_msmes", lambda key, **_: self.custom.get(key, [])), \
                patch.object(scoring, "get_scoring_anchors", lambda *_: (self.anchors, [])):
            yield

    def scan(self, lat, lon, business, radius=340):
        with contextlib.redirect_stdout(io.StringIO()):
            return perform_analysis(AnalysisRequest(lat=lat, lon=lon, business_type=business, radius=radius, user_id=None))


def percentile(sorted_values, share):
    return sorted_values[min(len(sorted_values) - 1, int(share * len(sorted_values)))]


def summarize(values):
    ordered = sorted(values)
    return {
        "mean": round(statistics.mean(ordered), 1),
        "p10": percentile(ordered, 0.10),
        "p50": percentile(ordered, 0.50),
        "p90": percentile(ordered, 0.90),
        "max": ordered[-1],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=float, default=0.003, help="grid spacing in degrees (0.003 is about 330 m)")
    parser.add_argument("--json", help="also save the results to this file")
    args = parser.parse_args()

    _load_ahp_weights_cache()
    # The scans below run with database connections refused, so load these first.
    preload_hazard_layer_cache()
    preload_zoning_layer_cache()
    scanner = Scanner()
    results = {}

    zoning_features = get_zoning_features()
    commercial_geometries = [
        feature["geometry"] for feature in zoning_features
        if any(word in feature["zone_class"] for word in COMMERCIAL_ZONES)
    ]
    # Keep only spots in the city: inside some zoning polygon, when a layer is active.
    points = grid_points(args.step)
    if zoning_features:
        points = [
            point for point in points
            if any(feature["geometry"].intersects(Point(point[1], point[0])) for feature in zoning_features)
        ]

    all_scores = []
    potentials_inside, potentials_outside = [], []
    factor_values = {factor: [] for factor in FACTORS}
    per_business = {}

    with scanner.patched():
        for business in MSME_CATEGORY_PROFILES:
            scores, potentials, verdicts = [], [], Counter()
            for lat, lon in points:
                report = scanner.scan(lat, lon, business)
                potential = report["market_potential_score"]
                scores.append(report["viability_score"])
                potentials.append(potential)
                verdicts[report["verdict"]["label"]] += 1
                inside = any(geometry.intersects(Point(lon, lat)) for geometry in commercial_geometries)
                (potentials_inside if inside else potentials_outside).append(potential)
                for factor in FACTORS:
                    value = report["breakdown"][factor]["score"]
                    if value is not None:
                        factor_values[factor].append(value)
            all_scores.extend(potentials)
            per_business[business] = {
                "potential": summarize(potentials),
                "viability": summarize(scores),
                "verdicts": dict(verdicts),
            }

        results["points_scanned"] = len(points)
        results["per_business"] = per_business
        results["factors"] = {factor: summarize(values) for factor, values in factor_values.items() if values}
        results["jenks_breaks"] = jenks_breaks(all_scores)
        results["current_cutoffs"] = (VERDICT_MODERATE_MIN, VERDICT_HIGH_MIN)
        if potentials_inside and potentials_outside:
            results["commercial_zone_check"] = {
                "mean_potential_inside": round(statistics.mean(potentials_inside), 1),
                "mean_potential_outside": round(statistics.mean(potentials_outside), 1),
            }

        # The pin-stability test.
        shift = 25.0 / METERS_PER_DEGREE
        sample = commercial_sample()
        worst_road = worst_total = 0.0
        road_moves_5, road_moves_10, total_moves_5, same_hazard_moves_5, worst_same_hazard = 0, 0, 0, 0, 0.0
        for lat, lon in sample:
            center = scanner.scan(lat, lon, "coffee")
            reports = [center] + [
                scanner.scan(lat + d_lat, lon + d_lon, "coffee")
                for d_lat, d_lon in ((shift, 0), (-shift, 0), (0, shift), (0, -shift))
            ]
            road_values = [report["breakdown"]["road_access"]["score"] for report in reports]
            total_values = [report["market_potential_score"] for report in reports]
            hazard_values = {report["breakdown"]["hazard"]["score"] for report in reports}
            road_range = max(road_values) - min(road_values)
            total_range = max(total_values) - min(total_values)
            worst_road = max(worst_road, road_range)
            worst_total = max(worst_total, total_range)
            road_moves_5 += road_range >= 5
            road_moves_10 += road_range >= 10
            total_moves_5 += total_range >= 5
            # A real flood-zone edge is a real change; everything else should be smooth.
            if len(hazard_values) == 1:
                worst_same_hazard = max(worst_same_hazard, total_range)
                same_hazard_moves_5 += total_range >= 5
        results["pin_stability"] = {
            "points": len(sample),
            "road_changed_5_or_more_pct": round(100 * road_moves_5 / len(sample), 1),
            "road_changed_10_or_more_pct": round(100 * road_moves_10 / len(sample), 1),
            "worst_road_range": round(worst_road, 1),
            "total_changed_5_or_more_pct": round(100 * total_moves_5 / len(sample), 1),
            "worst_total_range": worst_total,
            "total_changed_5_or_more_pct_away_from_flood_edges": round(100 * same_hazard_moves_5 / len(sample), 1),
            "worst_total_range_away_from_flood_edges": worst_same_hazard,
        }

        # The radius test: the score must not depend on the map view radius.
        radius_changes = 0
        for lat, lon in sample[::10]:
            values = {scanner.scan(lat, lon, "coffee", radius=radius)["viability_score"] for radius in (100, 340, 500, 1000, 1500)}
            radius_changes += len(values) > 1
        results["radius_test"] = {"points": len(sample[::10]), "points_where_radius_changed_the_score": radius_changes}

    print(json.dumps(results, indent=2))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2)


if __name__ == "__main__":
    main()
