"""Small SVG chart helpers for my dissertation-facing figures."""

import html
from pathlib import Path


SERIES = {
    "GPS ground truth": ("#111827", 3.0),
    "V1 baseline": ("#6b7280", 2.0),
    "V2 no-map": ("#d97706", 2.4),
    "V2 + OSM": ("#059669", 2.6),
}


def _header(width, height, title, subtitle=""):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/>
<text x="60" y="36" font-family="Arial" font-size="22" font-weight="bold">{html.escape(title)}</text>
<text x="60" y="58" font-family="Arial" font-size="13" fill="#4b5563">{html.escape(subtitle)}</text>
'''


def _path(points, transform):
    commands = []
    started = False

    for x, y in points:
        if x is None or y is None:
            started = False
            continue

        px, py = transform(x, y)

        if started:
            commands.append(f"L {px:.2f} {py:.2f}")
        else:
            commands.append(f"M {px:.2f} {py:.2f}")
            started = True

    return " ".join(commands)


def write_route_overlay(path, title, series):
    usable = [(name, points) for name, points in series if points]
    all_points = [
        point
        for _name, points in usable
        for point in points
        if point[0] is not None and point[1] is not None
    ]

    if not all_points:
        return False

    min_x = min(x for x, _ in all_points)
    max_x = max(x for x, _ in all_points)
    min_y = min(y for _, y in all_points)
    max_y = max(y for _, y in all_points)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    pad_x = max(span_x * 0.05, 30.0)
    pad_y = max(span_y * 0.05, 30.0)
    min_x -= pad_x
    max_x += pad_x
    min_y -= pad_y
    max_y += pad_y

    width, height, margin = 1120, 780, 75
    scale = min(
        (width - 2 * margin) / max(max_x - min_x, 1.0),
        (height - 2 * margin) / max(max_y - min_y, 1.0),
    )

    def transform(x, y):
        return (
            margin + (x - min_x) * scale,
            height - margin - (y - min_y) * scale,
        )

    svg = [_header(width, height, title, "Local X/Y metres; raw latitude/longitude are not shown.")]

    for name, points in usable:
        colour, stroke = SERIES.get(name, ("#374151", 2.0))
        svg.append(
            f'<path d="{_path(points, transform)}" fill="none" stroke="{colour}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round" opacity="0.92"/>'
        )

    x = 75
    for name, _points in usable:
        colour, stroke = SERIES.get(name, ("#374151", 2.0))
        svg.append(f'<line x1="{x}" y1="86" x2="{x+34}" y2="86" stroke="{colour}" stroke-width="{stroke+1}"/>')
        svg.append(f'<text x="{x+42}" y="90" font-family="Arial" font-size="12">{html.escape(name)}</text>')
        x += 190

    svg.append("</svg>")
    Path(path).write_text("".join(svg), encoding="utf-8")
    return True


def write_grouped_bar(path, title, categories, series, y_label):
    width, height = 1180, 720
    left, right, top, bottom = 95, 45, 95, 125
    chart_w = width - left - right
    chart_h = height - top - bottom
    values = [value for _name, data in series for value in data if value is not None]
    maximum = max(max(values) * 1.10 if values else 1.0, 1.0)
    svg = [_header(width, height, title, "Lower positional error is better.")]

    for tick in range(6):
        fraction = tick / 5.0
        value = maximum * fraction
        y = top + chart_h * (1.0 - fraction)
        svg.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#e5e7eb"/>')
        svg.append(f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" font-family="Arial" font-size="11">{value:.0f}</text>')

    group_w = chart_w / max(len(categories), 1)
    bar_space = group_w * 0.75
    bar_w = bar_space / max(len(series), 1)

    for ci, category in enumerate(categories):
        centre = left + group_w * (ci + 0.5)
        start_x = centre - bar_space / 2

        for si, (name, data) in enumerate(series):
            value = data[ci]
            if value is None:
                continue
            colour = SERIES.get(name, ("#374151", 2.0))[0]
            h = value / maximum * chart_h
            x = start_x + si * bar_w
            y = top + chart_h - h
            svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(bar_w-3,2):.1f}" height="{h:.1f}" fill="{colour}"/>')

        svg.append(f'<text x="{centre:.1f}" y="{height-bottom+24}" text-anchor="middle" font-family="Arial" font-size="10">{html.escape(category)}</text>')

    svg.append(f'<text x="24" y="{top+chart_h/2:.1f}" font-family="Arial" font-size="13" transform="rotate(-90 24 {top+chart_h/2:.1f})">{html.escape(y_label)}</text>')
    legend_x = left

    for name, _data in series:
        colour = SERIES.get(name, ("#374151", 2.0))[0]
        svg.append(f'<rect x="{legend_x}" y="{height-54}" width="16" height="12" fill="{colour}"/>')
        svg.append(f'<text x="{legend_x+22}" y="{height-44}" font-family="Arial" font-size="12">{html.escape(name)}</text>')
        legend_x += 190

    svg.append("</svg>")
    Path(path).write_text("".join(svg), encoding="utf-8")


def write_line_chart(path, title, series, x_label, y_label):
    usable = [(name, values) for name, values in series if values]
    if not usable:
        return False

    points = [point for _name, values in usable for point in values]
    max_x = max(max(x for x, _ in points), 1.0)
    max_y = max(max(y for _, y in points) * 1.05, 1.0)
    width, height = 1120, 700
    left, right, top, bottom = 95, 45, 95, 80
    chart_w = width - left - right
    chart_h = height - top - bottom

    def transform(x, y):
        return left + x / max_x * chart_w, top + chart_h - y / max_y * chart_h

    svg = [_header(width, height, title, "Error growth across the reconstructed journey.")]

    for tick in range(6):
        fraction = tick / 5.0
        x = left + chart_w * fraction
        y = top + chart_h * (1.0 - fraction)
        svg.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top+chart_h}" stroke="#eeeeee"/>')
        svg.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#eeeeee"/>')
        svg.append(f'<text x="{x:.1f}" y="{height-bottom+24}" text-anchor="middle" font-family="Arial" font-size="11">{max_x*fraction/1000:.1f}</text>')
        svg.append(f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" font-family="Arial" font-size="11">{max_y*fraction:.0f}</text>')

    for name, values in usable:
        colour, stroke = SERIES.get(name, ("#374151", 2.0))
        svg.append(f'<path d="{_path(values, transform)}" fill="none" stroke="{colour}" stroke-width="{stroke}" opacity="0.9"/>')

    svg.append(f'<text x="{left+chart_w/2:.1f}" y="{height-15}" text-anchor="middle" font-family="Arial" font-size="13">{html.escape(x_label)}</text>')
    svg.append(f'<text x="22" y="{top+chart_h/2:.1f}" font-family="Arial" font-size="13" transform="rotate(-90 22 {top+chart_h/2:.1f})">{html.escape(y_label)}</text>')
    svg.append("</svg>")
    Path(path).write_text("".join(svg), encoding="utf-8")
    return True
