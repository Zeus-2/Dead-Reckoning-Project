"""Build a self-contained local HTML showcase of my dissertation experiment."""

import csv
import html
import shutil
from pathlib import Path

from src.core.paths import newest_folder, open_html, resolve_cleaned_dataset, short_run_label, versioned_output_folder
from src.visualisation import results as visualise_results


def read_rows(path):
    path = Path(path)

    if not path.exists():
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def to_float(value):
    try:
        value = str(value).strip()
        return None if value == "" else float(value)
    except (TypeError, ValueError):
        return None


def average(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def metric(value, suffix=""):
    if value is None:
        return "N/A"
    return f"{value:,.1f}{suffix}"


def latest_behaviour_summary(cleaned_root):
    folder = newest_folder(cleaned_root, ("behaviour_analysis",))

    if folder is None:
        return []

    return read_rows(folder / "driving_behaviour_summary.csv")


def table(headers, rows):
    head = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    body = []

    for row in rows:
        body.append(
            "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row) + "</tr>"
        )

    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def run(cleaned_source):
    cleaned_root = resolve_cleaned_dataset(cleaned_source)
    visuals_folder, comparison = visualise_results.run(cleaned_root)
    output = versioned_output_folder(cleaned_root, "showcase")
    assets = output / "visuals"
    shutil.copytree(visuals_folder, assets)

    manifest = read_rows(cleaned_root / "dataset_manifest.csv")
    behaviour = latest_behaviour_summary(cleaned_root)
    primary = [row for row in manifest if row.get("status") == "PRIMARY DEAD RECKONING"]

    v1_mean = average(record["v1_rmse_m"] for record in comparison)
    v2_mean = average(record["v2_rmse_m"] for record in comparison)
    map_mean = average(record["v2_map_rmse_m"] for record in comparison)
    total_minutes = sum(to_float(row.get("duration_minutes")) or 0.0 for row in primary)
    total_miles = sum(to_float(row.get("distance_miles")) or 0.0 for row in primary)

    comparison_rows = []

    for record in comparison:
        comparison_rows.append([
            short_run_label(record["run"]),
            metric(record["v1_rmse_m"], " m"),
            metric(record["v2_rmse_m"], " m"),
            metric(record["v2_map_rmse_m"], " m"),
        ])

    behaviour_rows = []

    for row in behaviour:
        behaviour_rows.append([
            short_run_label(row.get("source_file", "")),
            row.get("mean_moving_speed_mph", ""),
            row.get("max_speed_mph", ""),
            row.get("p95_positive_acceleration_m_s2", ""),
            row.get("p95_braking_m_s2", ""),
            row.get("p95_absolute_turn_rate_deg_s", ""),
        ])

    route_cards = []

    for record in comparison:
        label = short_run_label(record["run"])
        route_path = assets / label / "route_progression.svg"
        error_path = assets / label / "error_over_distance.svg"

        if route_path.exists():
            route_cards.append(f'''<section class="route-card">
<h3>{html.escape(label)}</h3>
<img src="visuals/{html.escape(label)}/route_progression.svg" alt="Route progression for {html.escape(label)}">
{f'<img src="visuals/{html.escape(label)}/error_over_distance.svg" alt="Error over distance for {html.escape(label)}">' if error_path.exists() else ''}
</section>''')

    document = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vehicle Telemetry Dissertation Showcase</title>
<style>
:root {{ color-scheme: light; --ink:#111827; --muted:#596579; --line:#dfe4ea; --panel:#f7f8fa; --accent:#1f4e79; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Arial,Helvetica,sans-serif; color:var(--ink); background:#eef1f4; line-height:1.5; }}
main {{ max-width:1180px; margin:0 auto; background:white; min-height:100vh; padding:42px; }}
h1 {{ margin:0 0 8px; font-size:34px; }} h2 {{ margin-top:38px; border-bottom:2px solid var(--line); padding-bottom:8px; }}
h3 {{ margin-top:0; }} .subtitle {{ color:var(--muted); max-width:900px; }}
.grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin:26px 0; }}
.card {{ border:1px solid var(--line); background:var(--panel); padding:18px; border-radius:8px; }}
.card strong {{ display:block; font-size:26px; color:var(--accent); }} .card span {{ color:var(--muted); font-size:13px; }}
.progression {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }}
.step {{ border-left:4px solid var(--accent); padding:12px 14px; background:var(--panel); }}
img {{ width:100%; height:auto; border:1px solid var(--line); background:white; margin:8px 0 18px; }}
.route-card {{ margin:28px 0; page-break-inside:avoid; }}
.table-wrap {{ overflow-x:auto; }} table {{ width:100%; border-collapse:collapse; margin:14px 0 26px; font-size:13px; }}
th,td {{ border:1px solid var(--line); padding:8px 9px; text-align:left; }} th {{ background:var(--panel); }}
.note {{ border-left:4px solid #b7791f; background:#fff9e9; padding:12px 16px; }}
.actions {{ margin:18px 0; }} button {{ border:0; background:var(--accent); color:white; padding:10px 16px; border-radius:5px; cursor:pointer; font-size:14px; }}
@media (max-width:800px) {{ main {{ padding:22px; }} .grid,.progression {{ grid-template-columns:1fr 1fr; }} }}
@media (max-width:520px) {{ .grid,.progression {{ grid-template-columns:1fr; }} }}
@media print {{ body {{ background:white; }} main {{ max-width:none; padding:0; }} .actions {{ display:none; }} }}
</style>
</head>
<body>
<main>
<h1>Vehicle Telemetry Route Reconstruction</h1>
<p class="subtitle">My final local showcase of the MSc project: privacy-aware telemetry preparation, baseline and improved dead reckoning, OSM-assisted reconstruction, quantitative GPS evaluation and descriptive driving-behaviour features.</p>
<div class="actions"><button onclick="window.print()">Print / save as PDF</button></div>

<div class="grid">
<div class="card"><strong>{len(primary)}</strong><span>Primary journeys</span></div>
<div class="card"><strong>{total_minutes:.1f}</strong><span>Primary minutes</span></div>
<div class="card"><strong>{total_miles:.1f}</strong><span>Primary miles</span></div>
<div class="card"><strong>{len(manifest)}</strong><span>Total recordings retained/classified</span></div>
</div>

<h2>Method progression</h2>
<div class="progression">
<div class="step"><b>V1 baseline</b><br>Constant stationary gyro bias + OBD speed integration.</div>
<div class="step"><b>V2 no-map</b><br>Time-varying bias, robust filtering and quality-gated magnetometer heading-change fusion.</div>
<div class="step"><b>V2 + OSM</b><br>Known start anchor + topology-aware beam-search road constraints.</div>
</div>
<p class="note">GPS after the initial map anchor is evaluation ground truth. I do not use GPS bearing or the later GPS route to construct the inferred trajectory.</p>

<h2>Aggregate reconstruction results</h2>
<div class="grid">
<div class="card"><strong>{metric(v1_mean, ' m')}</strong><span>Mean V1 RMSE</span></div>
<div class="card"><strong>{metric(v2_mean, ' m')}</strong><span>Mean V2 no-map RMSE</span></div>
<div class="card"><strong>{metric(map_mean, ' m')}</strong><span>Mean V2 + OSM RMSE</span></div>
<div class="card"><strong>Local X/Y</strong><span>Privacy-safe geographic outputs</span></div>
</div>
<img src="visuals/rmse_comparison.svg" alt="RMSE comparison by run">
<img src="visuals/final_error_comparison.svg" alt="Final position error comparison by run">
{table(['Run','V1 RMSE','V2 no-map RMSE','V2 + OSM RMSE'], comparison_rows)}

<h2>Dataset overview</h2>
{('<img src="visuals/primary_dataset_duration.svg" alt="Primary dataset duration">' if (assets / 'primary_dataset_duration.svg').exists() else '')}
<p>I separate substantial primary journeys from supplementary, preliminary and unusable recordings. This keeps early feasibility work in the audit trail without treating every short test as equivalent evidence.</p>

<h2>Route-by-route visual comparison</h2>
{''.join(route_cards)}

<h2>Driving-behaviour features</h2>
<p>I report descriptive telemetry features rather than labelling a driver as aggressive or safe. These features are suitable for comparing recordings while acknowledging the logger's modest sample rate.</p>
{table(['Run','Mean moving speed (mph)','Max speed (mph)','P95 acceleration (m/s²)','P95 braking (m/s²)','P95 turn rate (deg/s)'], behaviour_rows) if behaviour_rows else '<p>Run the behaviour-analysis option to populate this section.</p>'}

<h2>Interpretation</h2>
<p>The version progression is part of the result. A more complicated reconstruction is not assumed to be better: I retain error metrics for each version so improvements and regressions remain visible. The OSM stage is therefore evaluated as an experimental constraint rather than treated as ground truth.</p>
<p>The experiment is a single-vehicle case study using an F56 Mini Cooper and commodity logging. The results demonstrate feasibility and limitations for this setup; they are not presented as accuracy guarantees for all vehicles.</p>
</main>
</body>
</html>'''

    index = output / "index.html"
    index.write_text(document, encoding="utf-8")
    return output, index


def main(default_source=None):
    print()
    print("Build My Dissertation Showcase")
    print("=" * 42)

    if default_source is not None:
        print("My default cleaned dataset is:")
        print(f"  {default_source}")
        print("Press Enter to use it, or type another cleaned dataset.")

    raw = input("Cleaned dataset: ").strip().strip('"')

    if not raw and default_source is not None:
        raw = str(default_source)

    if not raw:
        print("Cancelled.")
        return None

    try:
        output, index = run(raw)
    except Exception as error:
        print(f"[ERROR] {error}")
        return None

    print("\nMy showcase is ready:")
    print(f"  {index}")
    open_html(index)
    return output


if __name__ == "__main__":
    main()
