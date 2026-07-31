#!/usr/bin/env python3
"""Convert Excalidraw JSON diagrams to clean, self-contained SVG."""

import json
import sys
from pathlib import Path


def hex_alpha(hex_color):
    if not hex_color or hex_color in ("transparent", "none"):
        return "none"
    h = hex_color.strip()
    if len(h) == 9:
        r = int(h[1:3], 16)
        g = int(h[3:5], 16)
        b = int(h[5:7], 16)
        a = round(int(h[7:9], 16) / 255, 2)
        return f"rgba({r},{g},{b},{a})"
    if len(h) == 5:
        r = int(h[1] + h[1], 16)
        g = int(h[2] + h[2], 16)
        b = int(h[3] + h[3], 16)
        a = round(int(h[4] + h[4], 16) / 255, 2)
        return f"rgba({r},{g},{b},{a})"
    return h


def compute_bounds(elements):
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for el in elements:
        if el.get("isDeleted") or "type" not in el:
            continue
        x, y = el.get("x", 0), el.get("y", 0)
        w, h = el.get("width", 0), el.get("height", 0)
        if el.get("type") == "arrow":
            for px, py in el.get("points", []):
                ax, ay = x + px, y + py
                min_x = min(min_x, ax)
                min_y = min(min_y, ay)
                max_x = max(max_x, ax)
                max_y = max(max_y, ay)
        else:
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + w)
            max_y = max(max_y, y + h)
    pad = 40
    return (min_x - pad, min_y - pad, max_x - min_x + 2 * pad, max_y - min_y + 2 * pad)


def arrow_colors(elements):
    colors = set()
    for el in elements:
        if el.get("isDeleted") or el.get("type") != "arrow":
            continue
        if el.get("endArrowhead") or el.get("startArrowhead"):
            colors.add(el.get("strokeColor", "#000"))
    return sorted(colors)


def dash_attr(el):
    s = el.get("strokeStyle", "solid")
    return ' stroke-dasharray="8,4"' if s in ("dashed",) else ""


def render_rect(el):
    x, y = el["x"], el["y"]
    w, h = el["width"], el["height"]
    fill = hex_alpha(el.get("backgroundColor", "transparent"))
    stroke = el.get("strokeColor", "#000")
    sw = el.get("strokeWidth", 1)
    op = el.get("opacity", 100) / 100
    rn = el.get("roundness")
    rx = 0
    if rn and isinstance(rn, dict) and rn.get("type") in (3, "perimeter"):
        rx = min(w, h) * 0.2
    elif isinstance(rn, (int, float)):
        rx = rn
    a = f'x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"'
    if rx:
        a += f' rx="{rx:.1f}" ry="{rx:.1f}"'
    if op < 1:
        a += f' opacity="{op}"'
    a += dash_attr(el)
    return f"    <rect {a} />"


def render_text(el):
    text = el.get("text", "").strip()
    if not text:
        return ""
    x, y = el["x"], el["y"]
    w, h = el["width"], el["height"]
    fs = el.get("fontSize", 14)
    color = el.get("strokeColor", "#000")
    align = el.get("textAlign", "left")
    valign = el.get("verticalAlign", "top")
    op = el.get("opacity", 100) / 100
    ff = el.get("fontFamily", 5)
    families = {
        3: "monospace,'Courier New',Courier",
        5: "system-ui,'Segoe UI',Roboto,Helvetica,Arial,sans-serif",
    }
    lines = text.split("\n")
    lh = fs * 1.3
    anchor = {"left": "start", "center": "middle", "right": "end"}[align]
    tx = x + w / 2 if align == "center" else (x + w if align == "right" else x)
    total_h = len(lines) * lh
    if valign == "middle":
        ty = y + (h - total_h) / 2 + fs * 0.85
    elif valign == "bottom":
        ty = y + h - total_h + fs * 0.85
    else:
        ty = y + fs * 0.85
    style = f"font-size:{fs}px;font-family:{families.get(ff,families[5])};fill:{color}"
    if op < 1:
        style += f";opacity:{op}"
    tspans = []
    for i, line in enumerate(lines):
        esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;") or " "
        dy = 0 if i == 0 else lh
        tspans.append(f'        <tspan x="{tx}" dy="{dy}">{esc}</tspan>')
    t = "\n".join(tspans)
    return f'    <text x="{tx}" y="{ty:.1f}" text-anchor="{anchor}" style="{style}">\n{t}\n    </text>'


def render_arrow(el):
    x, y = el["x"], el["y"]
    pts = el.get("points", [])
    if not pts:
        return ""
    abs_pts = [(x + px, y + py) for px, py in pts]
    parts = [f'{"M" if i==0 else "L"} {ax:.1f} {ay:.1f}' for i, (ax, ay) in enumerate(abs_pts)]
    d = " ".join(parts)
    stroke = el.get("strokeColor", "#000")
    sw = el.get("strokeWidth", 1)
    op = el.get("opacity", 100) / 100
    safe = stroke.replace("#", "")
    marker = f' marker-end="url(#a-{safe})"' if el.get("endArrowhead") else ""
    a = f'd="{d}" fill="none" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"'
    if op < 1:
        a += f' opacity="{op}"'
    a += dash_attr(el)
    return f"    <path {a}{marker} />"


def convert(input_path, output_path):
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)
    elements = [el for el in data.get("elements", []) if not el.get("isDeleted") and "type" in el]
    if not elements:
        print(f"No active elements in {input_path}")
        return
    ox, oy, w, h = compute_bounds(elements)
    colors = arrow_colors(elements)
    lines = ['<?xml version="1.0" encoding="utf-8"?>']
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{ox:.0f} {oy:.0f} {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}">'
    )
    lines.append("  <defs>")
    for c in colors:
        s = c.replace("#", "")
        lines.append(
            f'    <marker id="a-{s}" markerWidth="14" markerHeight="10" refX="12" refY="5" orient="auto" markerUnits="userSpaceOnUse">'
        )
        lines.append(f'      <polygon points="0 0, 14 5, 0 10" fill="{c}" />')
        lines.append("    </marker>")
    lines.append("  </defs>")
    lines.append("  <g>")
    for el in elements:
        t = el.get("type")
        if t == "rectangle":
            r = render_rect(el)
            if r:
                lines.append(r)
    for el in elements:
        t = el.get("type")
        if t == "arrow":
            r = render_arrow(el)
            if r:
                lines.append(r)
    for el in elements:
        t = el.get("type")
        if t == "text":
            r = render_text(el)
            if r:
                lines.append(r)
    lines.append("  </g>")
    lines.append("</svg>")
    out = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"  Written: {output_path}  ({len(elements)} elements, {w:.0f}x{h:.0f}px)")


def main():
    diag = Path(r"H:\rag-multi-agent-cluster\docs\diagrams")
    pairs = [
        ("01-cluster-overview.excalidraw", "01-cluster-overview.svg"),
        ("02-ingestion-flow.excalidraw", "02-ingestion-flow.svg"),
        ("03-query-flow.excalidraw", "03-query-flow.svg"),
        ("04-backup-321.excalidraw", "04-backup-321.svg"),
        ("05-network-topology.excalidraw", "05-network-topology.svg"),
        ("06-physical-topology.excalidraw", "06-physical-topology.svg"),
    ]
    for src_name, dst_name in pairs:
        src = diag / src_name
        dst = diag / dst_name
        if src.exists():
            print(f"Converting {src_name}...")
            convert(str(src), str(dst))
        else:
            print(f"  Source not found: {src}")


if __name__ == "__main__":
    main()
