import math
import json
import os
import re
from urllib import request
from urllib.error import URLError, HTTPError
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def _normalize_count_to_0_100(count: float, scale: float = 10.0) -> float:
    # logistic-like transform to keep values in 0-100
    try:
        v = 100.0 * (1.0 - 1.0 / (1.0 + (count / scale)))
    except Exception:
        v = 0.0
    return max(0.0, min(100.0, v))


def _normalize_distance_to_0_100(meters: float, decay: float = 500.0) -> float:
    # closer = higher score
    if meters is None:
        return 0.0
    try:
        v = 100.0 * math.exp(-max(0.0, meters) / decay)
    except Exception:
        v = 0.0
    return max(0.0, min(100.0, v))


def _confidence_sigma(confidence_score: float) -> float:
    # convert a 0-100 confidence to a small sigma (lower when confidence high)
    c = max(1.0, min(100.0, float(confidence_score or 50)))
    # map 100 -> 1.0, 50 -> 5.0, 0 -> 10.0 (arbitrary units)
    return 1.0 + (100.0 - c) * 0.09


def build_structured_report(analysis: Dict[str, Any], category_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert raw analysis output into a structured report object with scores, confidence, and sensitivity.
    Expects `analysis` to contain keys: competitors (list), anchors (list), roads (list), building_density, zoning_flags, hazards, target coordinates, radius, raw_scores
    """
    now = datetime.utcnow().isoformat() + 'Z'

    # Extract basic inputs
    competitors = analysis.get('competitors', []) or []
    anchors = analysis.get('anchors', []) or []
    roads = analysis.get('roads', []) or []
    building_density = analysis.get('building_density', None)
    zoning_flags = analysis.get('zoning_flags', {}) or {}
    hazards = analysis.get('hazards', {}) or {}
    coords = {
        'latitude': analysis.get('target_lat') or analysis.get('latitude'),
        'longitude': analysis.get('target_lon') or analysis.get('longitude')
    }

    # Normalize inputs
    competitor_count = len(competitors)
    competitors_score = _normalize_count_to_0_100(competitor_count, scale=category_profile.get('competitor_scale', 8.0))

    # anchor proximity: use nearest anchor distance if provided in anchors list as dicts with distance_m
    nearest_anchor_m = None
    for a in anchors:
        d = a.get('distance_m') if isinstance(a, dict) else None
        if d is not None:
            if nearest_anchor_m is None or d < nearest_anchor_m:
                nearest_anchor_m = d
    anchor_score = _normalize_distance_to_0_100(nearest_anchor_m or 1e6, decay=category_profile.get('anchor_decay_m', 800.0))

    # road access: prefer highest class in roads list
    road_quality = 0.0
    for r in roads:
        rc = (r.get('road_class') or r.get('type') or '').lower() if isinstance(r, dict) else ''
        if 'motorway' in rc or 'trunk' in rc:
            road_quality = max(road_quality, 100.0)
        elif 'primary' in rc:
            road_quality = max(road_quality, 80.0)
        elif 'secondary' in rc:
            road_quality = max(road_quality, 60.0)
        elif 'tertiary' in rc:
            road_quality = max(road_quality, 40.0)
        elif rc:
            road_quality = max(road_quality, 20.0)
    # fallback if none
    if not roads:
        road_quality = 10.0

    # building density normalization
    b_density_score = 0.0
    if building_density is not None:
        try:
            # assume building_density is buildings per hectare
            b_density_score = max(0.0, min(100.0, (building_density / (category_profile.get('building_density_scale', 50.0))) * 100.0))
        except Exception:
            b_density_score = 0.0

    # Weighted aggregation per subscore
    weights = category_profile.get('weights', {
        'competition': 0.35,
        'access': 0.25,
        'demand_anchor': 0.2,
        'density': 0.1,
        'zoning_hazard': 0.1
    })

    # Zoning/hazard penalty: compute 0-100 where higher means better (no hazards/no restrictions)
    zoning_penalty = 0.0
    if zoning_flags.get('restricted'):
        zoning_penalty -= 40.0
    if hazards.get('flood_prone'):
        zoning_penalty -= 30.0
    zoning_score = max(0.0, 100.0 + zoning_penalty)

    # Combine into final viability (higher is better). Competition reduces viability.
    competition_component = (100.0 - competitors_score) * weights.get('competition', 0.35)
    access_component = road_quality * weights.get('access', 0.25)
    anchor_component = anchor_score * weights.get('demand_anchor', 0.2)
    density_component = b_density_score * weights.get('density', 0.1)
    zoning_component = zoning_score * weights.get('zoning_hazard', 0.1)

    raw_final = competition_component + access_component + anchor_component + density_component + zoning_component
    final_score = max(0.0, min(100.0, raw_final))

    # Uncertainty: derive sigma from inputs confidences (if competitors/anchors have confidence)
    sigmas = []
    for c in competitors:
        sigmas.append(_confidence_sigma(c.get('confidence_score', 50) if isinstance(c, dict) else 50))
    for a in anchors:
        sigmas.append(_confidence_sigma(a.get('confidence_score', 50) if isinstance(a, dict) else 50))
    for r in roads:
        sigmas.append(_confidence_sigma(r.get('confidence_score', 50) if isinstance(r, dict) else 50))
    sigmas.append(_confidence_sigma(50))
    # simple pooled sigma
    pooled_sigma = math.sqrt(sum([s * s for s in sigmas]) / max(1, len(sigmas)))

    # Sensitivity: finite difference for competitor_count +/-1
    def _sens_delta_competitor(delta=1):
        c_score = _normalize_count_to_0_100(max(0, competitor_count + delta), scale=category_profile.get('competitor_scale', 8.0))
        comp = (100.0 - c_score) * weights.get('competition', 0.35)
        return comp - competition_component

    sens_competitor = _sens_delta_competitor(1)
    sens_anchor = 0.0
    # if nearest_anchor_m exists, compute delta by moving it closer by 100m
    if nearest_anchor_m is not None:
        a_score_now = _normalize_distance_to_0_100(nearest_anchor_m, decay=category_profile.get('anchor_decay_m', 800.0))
        a_score_then = _normalize_distance_to_0_100(max(0.0, nearest_anchor_m - 100.0), decay=category_profile.get('anchor_decay_m', 800.0))
        sens_anchor = (a_score_then - a_score_now) * weights.get('demand_anchor', 0.2)

    sensitivity = {
        'competitor_plus1_effect': sens_competitor,
        'anchor_minus100m_effect': sens_anchor
    }

    structured = {
        'generated_at': now,
        'target_coordinates': coords,
        'category_profile': category_profile,
        'inputs': {
            'competitor_count': competitor_count,
            'competitors': competitors,
            'anchors': anchors,
            'roads': roads,
            'building_density': building_density,
            'zoning_flags': zoning_flags,
            'hazards': hazards,
            'radius': analysis.get('radius')
        },
        'scores': {
            'competitors_score': competitors_score,
            'access_score': road_quality,
            'anchor_score': anchor_score,
            'building_density_score': b_density_score,
            'zoning_score': zoning_score,
            'final_viability_score': final_score,
            'final_sigma': pooled_sigma
        },
        'sensitivity': sensitivity,
        'recommendation': {
            'text': None,
            'reasoning': []
        }
    }

    # simple rule-based recommendations
    recs = []
    if final_score > 70 and not zoning_flags.get('restricted', False) and not hazards.get('flood_prone', False):
        recs.append('Viable site: proceed with small pilot and market test.')
    if final_score <= 70:
        recs.append('Consider mitigation: reduce footprint, niche offering, or search nearby lower-competition sites.')
    if competitor_count > category_profile.get('competitor_high_threshold', 8):
        recs.append('High local competition — recommend differentiated offering or increased marketing budget.')

    structured['recommendation']['text'] = recs[0] if recs else 'No strong recommendation.'
    structured['recommendation']['reasoning'] = recs

    return structured


def render_report_html(structured: Dict[str, Any]) -> str:
    # deterministic HTML renderer for the structured object
    s = structured
    coords = s.get('target_coordinates') or {}
    scores = s.get('scores', {})
    rec = s.get('recommendation', {})

    def badge_html(label: str, score: float) -> str:
        color = '#16a34a' if score >= 70 else ('#f59e0b' if score >= 40 else '#ef4444')
        return f'<span style="background:{color};color:#fff;padding:6px 10px;border-radius:6px;margin-right:8px;font-weight:600">{label}: {round(score)}</span>'

    html = [
        '<!doctype html>',
        '<html><head><meta charset="utf-8"><title>MarketScope Feasibility Report</title>',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<style>body{font-family:Arial,Helvetica,sans-serif;color:#111;margin:0;padding:18px} .title{display:flex;justify-content:space-between;align-items:center} .section{margin-top:18px;padding:12px;border-radius:8px;border:1px solid #eee;background:#fff}</style>',
        '</head><body>',
        f'<div class="title"><h1>Feasibility Report</h1><div>Generated: {s.get("generated_at")}</div></div>',
        f'<div style="margin-top:6px;color:#444">Location: {coords.get("latitude")},{coords.get("longitude")}</div>',
        '<div class="section">',
        '<h2>Executive Summary</h2>',
        f'<p><strong>Recommendation:</strong> {rec.get("text")}</p>',
        '</div>',
        '<div class="section">',
        '<h2>Score Breakdown</h2>',
        '<div>' + badge_html('Viability', scores.get('final_viability_score', 0)) + '</div>',
        '<ul>',
        f'<li>Competition Score: {round(scores.get("competitors_score",0))}</li>',
        f'<li>Access Score: {round(scores.get("access_score",0))}</li>',
        f'<li>Anchor Proximity Score: {round(scores.get("anchor_score",0))}</li>',
        f'<li>Building Density Score: {round(scores.get("building_density_score",0))}</li>',
        f'<li>Zoning/Hazard Score: {round(scores.get("zoning_score",0))}</li>',
        '</ul>',
        '</div>',
        '<div class="section">',
        '<h2>Site Map / Anchor Context</h2>',
        '<p>Map snapshot not available in offline report. Embed a map image in production.</p>',
        '</div>',
        '<div class="section">',
        '<h2>Recommendation & Next Actions</h2>',
        '<ol>',
        ''.join(f'<li>{r}</li>' for r in (rec.get('reasoning') or [])),
        '</ol>',
        '</div>',
        '<div style="margin-top:18px;color:#777;font-size:12px">Report generated by MarketScope reporting engine.</div>',
        '</body></html>'
    ]

    return '\n'.join(html)


def try_render_pdf_bytes(html: str) -> Optional[bytes]:
    try:
        # use weasyprint if available
        from weasyprint import HTML
        doc = HTML(string=html)
        return doc.write_pdf()
    except Exception:
        return None


def build_llm_prompt_payload(structured: Dict[str, Any], business_type: str = '') -> Dict[str, str]:
    system_prompt = (
        "You are a friendly business location advisor for new Panabo MSME entrepreneurs. "
        "Write in a gentle, simple, and clear tone aimed at people new to business. "
        "Prefer short sentences and common words. Never invent facts or numbers; use only the data provided. "
        "When using an uncommon or technical word, add a short definition in parentheses immediately after the word. "
        "If you must state assumptions, label them clearly and keep them brief."
    )

    payload = {
        'business_type': business_type,
        'coordinates': structured.get('target_coordinates', {}),
        'scores': structured.get('scores', {}),
        'zoning_hazard': {
            'zoning_flags': (structured.get('inputs') or {}).get('zoning_flags', {}),
            'hazards': (structured.get('inputs') or {}).get('hazards', {}),
        },
        'anchor_summary': {
            'anchor_count': len((structured.get('inputs') or {}).get('anchors') or []),
            'anchor_score': (structured.get('scores') or {}).get('anchor_score'),
        },
        'competitor_count': (structured.get('inputs') or {}).get('competitor_count'),
        'category_sensitivity': structured.get('sensitivity', {}),
        'recommendation_seed': structured.get('recommendation', {}),
    }

    user_prompt = (
        "Generate a feasibility report with these sections in this exact order:\n"
        "1) Executive Summary\n"
        "2) Location Snapshot\n"
        "3) Zoning Status\n"
        "4) Hazard Status\n"
        "5) Saturation Assessment\n"
        "6) Demand and Anchor Commentary\n"
        "7) Recommendation\n"
        "8) Next Actions\n\n"
        "Use only the data below (JSON):\n"
        f"{json.dumps(payload, ensure_ascii=True)}\n\n"
        "Constraints:\n"
        "- Keep it concise, gentle, and easy to read for new entrepreneurs. Use common words.\n"
        "- If you use a technical term, include a one-line plain-language definition in parentheses immediately after the term.\n"
        "- Include key numeric values exactly as provided.\n"
        "- Use only the data below (do not add or invent facts).\n"
        "- Do not include markdown code fences.\n"
        "- Do not output JSON."
    )

    return {
        'system_prompt': system_prompt,
        'user_prompt': user_prompt,
    }


def generate_deterministic_narrative(structured: Dict[str, Any], business_type: str = '') -> str:
    s = structured
    scores = s.get('scores', {}) or {}
    inputs = s.get('inputs', {}) or {}
    zoning_flags = inputs.get('zoning_flags', {}) or {}
    hazards = inputs.get('hazards', {}) or {}
    recommendation = s.get('recommendation', {}) or {}
    final = round(scores.get('final_viability_score', 0), 1)
    sigma = round(float(scores.get('final_sigma', 0) or 0), 2)
    competitors = int((inputs.get('competitor_count') or 0))

    # Identify weakest sub-scores for targeted recommendations
    sub_scores = {
        'competition': float(scores.get('competitors_score') or 0),
        'access': float(scores.get('access_score') or 0),
        'anchors': float(scores.get('anchor_score') or 0),
        'density': float(scores.get('building_density_score') or 0),
        'zoning': float(scores.get('zoning_score') or 0),
    }
    weakest = sorted(sub_scores.items(), key=lambda kv: kv[1])[:2]

    lines: List[str] = []
    lines.append('Executive Summary')
    # simple definition for viability and sigma for new entrepreneurs
    lines.append(f"This report looks at the selected place for {business_type or 'your business'}.")
    lines.append(f"Viability score: {final} (±{sigma}) — (viability: a simple measure of how likely the site is to do well; sigma: estimated uncertainty).")
    lines.append("")

    lines.append('Location Snapshot')
    lat = ((s.get('target_coordinates') or {}).get('latitude'))
    lon = ((s.get('target_coordinates') or {}).get('longitude'))
    lines.append(f"Location: {lat if lat is not None else 'N/A'}, {lon if lon is not None else 'N/A'}.")
    lines.append(f"Scan radius: {inputs.get('radius') or 'N/A'} meters. Competitors found: {competitors}.")
    lines.append("")

    lines.append('Zoning Status')
    lines.append(f"Restricted zoning: {'Yes' if zoning_flags.get('restricted') else 'No'}.")
    lines.append("")

    lines.append('Hazard Status')
    lines.append(f"Flood-prone area: {'Yes' if hazards.get('flood_prone') else 'No'}.")
    lines.append("")

    lines.append('Saturation Assessment')
    lines.append(f"Competition level: {round(sub_scores['competition'], 1)} (higher = more competitors nearby).")
    lines.append("")

    lines.append('Demand and Anchor Commentary')
    lines.append(f"Nearby demand score: {round(sub_scores['anchors'], 1)}. Access score: {round(sub_scores['access'], 1)}.")
    lines.append("")

    lines.append('Interpretation & Insights')
    if final >= 70:
        lines.append('This looks promising. You can try a small test (pilot) for a few weeks to see real customer interest.')
        lines.append('Start small: short lease or pop-up, simple tracking of visitors and sales.')
    elif final >= 50:
        lines.append('This could work with care. Run a low-cost test and focus on something different from nearby shops.')
        lines.append('Try special offers or a small menu to learn what customers prefer.')
    else:
        lines.append('This site looks challenging right now. Consider looking nearby for quieter spots or a different product idea.')
        lines.append('If you stay, test on a very small scale before committing.')

    # Sensitivity insights (kept simple)
    sens = s.get('sensitivity', {}) or {}
    if sens:
        lines.append("")
        lines.append('Confidence & Sensitivity')
        lines.append(f"Estimated uncertainty (sigma): {sigma} (smaller means more confidence).")
        comp_effect = round(float(sens.get('competitor_plus1_effect', 0)), 3)
        anchor_effect = round(float(sens.get('anchor_minus100m_effect', 0)), 3)
        lines.append(f"One more nearby competitor changes the score by: {comp_effect:+} points.")
        lines.append(f"Being 100m closer to a strong anchor changes the score by: {anchor_effect:+} points.")

    # Key weaknesses
    lines.append("")
    lines.append('Key Weaknesses')
    for k, v in weakest:
        # keep wording very simple
        lines.append(f"- {k.title()}: {round(v,1)}")

    # Recommendations
    lines.append("")
    lines.append('Recommendation')
    # rewrite recommendation text to be simple if present
    rec_text = recommendation.get('text') or 'No strong recommendation.'
    # keep original suggestion but make phrasing simpler
    lines.append(rec_text)

    # Next actions: prioritized list
    lines.append("")
    lines.append('Next Actions')
    next_steps: List[str] = []
    # If coordinates missing, recommend field survey first
    coords = s.get('target_coordinates') or {}
    if not coords.get('latitude') or not coords.get('longitude'):
        next_steps.append('Perform a short field survey to validate coordinates and capture photos.')

    if final >= 70:
        next_steps += [
            'Negotiate short pilot lease or pop-up space (3 months).',
            'Set up simple footfall and sales tracking.',
            'Engage local suppliers and test pricing strategies.'
        ]
    elif final >= 50:
        next_steps += [
            'Run a low-cost pilot (market stall or pop-up).',
            'Conduct a 2-week price/promotions experiment.',
            'Survey 30–50 local customers for preferences.'
        ]
    else:
        next_steps += [
            'Scan adjacent blocks for lower-competition pockets.',
            'Consider a differentiated or delivery-focused model.',
            'Collect anchor and footfall data before committing.'
        ]

    # Add targeted fixes for weakest components
    for k, _ in weakest:
        if k == 'competition':
            next_steps.append('If competition is high, audit competitors for gaps (hours, offerings, price).')
        if k == 'access':
            next_steps.append('If access is weak, evaluate signage, last-mile delivery access, and parking options.')
        if k == 'anchors':
            next_steps.append('If anchor proximity is low, identify nearby demand generators (markets, schools) to target.')

    # Ensure at least one actionable item
    if not next_steps:
        next_steps.append('Validate assumptions through a short field survey.')

    for idx, step in enumerate(next_steps, start=1):
        lines.append(f"{idx}. {step}")

    # Data gaps
    lines.append("")
    lines.append('Data Gaps & Suggested Data Collection')
    if competitors == 0:
        lines.append('- No competitors detected in scan — verify with a field sweep or extend scan radius.')
    if inputs.get('building_density') is None:
        lines.append('- Missing building density — capture building counts per hectare for demand estimate.')

    # TL;DR and KPIs
    try:
        tldr = None
        if final >= 70:
            tldr = 'Strong candidate for pilot; low immediate risk.'
        elif final >= 50:
            tldr = 'Possibly viable with validation; run a targeted pilot.'
        else:
            tldr = 'Low viability; prioritize scanning nearby alternatives or niche pivots.'

        lines.insert(2, '')
        lines.insert(2, f'TL;DR: {tldr}')

        lines.append("")
        lines.append('Suggested KPIs to track during validation')
        kpis = [
            'Footfall (visitors/day)',
            'Conversion rate (visitors -> purchase)',
            'Average transaction value (PHP)',
            'Daily sales (PHP)'
        ]
        for k in kpis:
            lines.append(f'- {k}')

        # Add effort estimates (Low/Med/High) for each next step
        lines.append("")
        lines.append('Estimated effort for next steps (Low/Med/High)')
        effort_map = {}
        for s in next_steps:
            effort = 'Low'
            if any(w in s.lower() for w in ['negotiate','lease','collect']):
                effort = 'Medium'
            if any(w in s.lower() for w in ['scan adjacent','field survey','survey 30']):
                effort = 'Low'
            if any(w in s.lower() for w in ['audit competitors','identify nearby']):
                effort = 'Low'
            effort_map[s] = effort
            lines.append(f'- [{effort}] {s}')
    except Exception:
        # non-fatal: leave narrative as-is
        pass

    return "\n".join(lines)


def generate_gemini_narrative(structured: Dict[str, Any], business_type: str = '', model: str = 'gemini-1.5-pro') -> Dict[str, Any]:
    api_key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not api_key:
        return {
            'ok': False,
            'error': 'Missing GEMINI_API_KEY',
            'narrative': None,
            'provider': 'gemini',
            'model': model,
        }

    prompts = build_llm_prompt_payload(structured, business_type=business_type)
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    body = {
        'system_instruction': {
            'parts': [{'text': prompts['system_prompt']}]
        },
        'contents': [
            {'role': 'user', 'parts': [{'text': prompts['user_prompt']}]}]
    }

    req = request.Request(
        endpoint,
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )

    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode('utf-8')
            parsed = json.loads(raw)
    except HTTPError as e:
        return {
            'ok': False,
            'error': f'Gemini HTTP error: {e.code}',
            'narrative': None,
            'provider': 'gemini',
            'model': model,
        }
    except URLError:
        return {
            'ok': False,
            'error': 'Gemini network error',
            'narrative': None,
            'provider': 'gemini',
            'model': model,
        }
    except Exception as e:
        return {
            'ok': False,
            'error': f'Gemini parse error: {str(e)}',
            'narrative': None,
            'provider': 'gemini',
            'model': model,
        }

    text = None
    candidates = parsed.get('candidates') or []
    if candidates:
        content = (candidates[0] or {}).get('content') or {}
        for part in (content.get('parts') or []):
            maybe = part.get('text') if isinstance(part, dict) else None
            if maybe:
                text = maybe
                break

    if not text:
        return {
            'ok': False,
            'error': 'Gemini returned empty narrative',
            'narrative': None,
            'provider': 'gemini',
            'model': model,
        }

    return {
        'ok': True,
        'error': None,
        'narrative': text.strip(),
        'provider': 'gemini',
        'model': model,
    }


def quality_control_narrative(narrative: str, structured: Dict[str, Any]) -> Dict[str, Any]:
    required_headings = [
        'Executive Summary',
        'Location Snapshot',
        'Zoning Status',
        'Hazard Status',
        'Saturation Assessment',
        'Demand and Anchor Commentary',
        'Recommendation',
        'Next Actions',
    ]
    warnings: List[str] = []
    reviewed = narrative or ''

    for heading in required_headings:
        if heading.lower() not in reviewed.lower():
            warnings.append(f'Missing heading: {heading}')
            reviewed += f"\n\n{heading}\n[Section auto-inserted by QC. Please regenerate for richer detail.]"

    expected_competitors = int(((structured.get('inputs') or {}).get('competitor_count') or 0))
    expected_viability = round(float(((structured.get('scores') or {}).get('final_viability_score') or 0)), 1)

    competitor_mentions = re.findall(r'competitor[s]?\s*(?:count|observed)?\s*[:=]?\s*(\d+)', reviewed, flags=re.IGNORECASE)
    if competitor_mentions:
        if int(competitor_mentions[0]) != expected_competitors:
            warnings.append('Competitor count mismatch against structured input')

    viability_mentions = re.findall(r'viability\s*score\s*[:=]?\s*(\d+(?:\.\d+)?)', reviewed, flags=re.IGNORECASE)
    if viability_mentions:
        if abs(float(viability_mentions[0]) - expected_viability) > 0.2:
            warnings.append('Viability score mismatch against structured input')

    return {
        'narrative': reviewed.strip(),
        'warnings': warnings,
        'valid': len(warnings) == 0,
    }


def generate_narrative_with_fallback(
    structured: Dict[str, Any],
    business_type: str = '',
    use_llm: bool = True,
    gemini_model: str = 'gemini-1.5-pro',
) -> Dict[str, Any]:
    llm_meta: Dict[str, Any] = {
        'used_llm': False,
        'provider': None,
        'model': None,
        'fallback_reason': None,
    }

    if use_llm:
        llm_result = generate_gemini_narrative(structured, business_type=business_type, model=gemini_model)
        if llm_result.get('ok') and llm_result.get('narrative'):
            qc = quality_control_narrative(llm_result['narrative'], structured)
            llm_meta.update({
                'used_llm': True,
                'provider': llm_result.get('provider'),
                'model': llm_result.get('model'),
                'fallback_reason': None if qc.get('valid') else 'qc_warnings',
            })
            if qc.get('valid'):
                return {'narrative': qc['narrative'], 'qc': qc, 'meta': llm_meta}

            # Keep LLM text even with warnings, but still provide deterministic fallback as backup.
            deterministic = generate_deterministic_narrative(structured, business_type=business_type)
            return {
                'narrative': qc['narrative'],
                'qc': qc,
                'meta': llm_meta,
                'deterministic_backup': deterministic,
            }

        llm_meta.update({
            'used_llm': False,
            'provider': llm_result.get('provider'),
            'model': llm_result.get('model'),
            'fallback_reason': llm_result.get('error') or 'llm_failed',
        })

    deterministic = generate_deterministic_narrative(structured, business_type=business_type)
    qc = quality_control_narrative(deterministic, structured)
    return {'narrative': qc['narrative'], 'qc': qc, 'meta': llm_meta}
