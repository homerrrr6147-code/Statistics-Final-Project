from __future__ import annotations

import json
import hashlib
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
}


def natural_key(name: str) -> list[object]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def texts(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    return [node.text or "" for node in root.findall(".//a:t", NS)]


def chart_payload(xml_bytes: bytes) -> dict[str, object]:
    root = ET.fromstring(xml_bytes)
    series = []
    for ser in root.findall(".//c:ser", NS):
        name_nodes = ser.findall(".//c:tx//c:v", NS)
        name = name_nodes[0].text if name_nodes else ""
        category_nodes = ser.findall(".//c:cat//c:v", NS)
        categories = [node.text or "" for node in category_nodes]
        value_nodes = ser.findall(".//c:val//c:v", NS)
        values = [float(node.text) for node in value_nodes if node.text]
        series.append({"name": name, "categories": categories, "values": values})
    return {"series": series}


def main() -> int:
    deck = Path(sys.argv[1]).resolve()
    out_dir = Path(sys.argv[2]).resolve()
    source_deck = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(deck) as zf:
        names = set(zf.namelist())
        slide_names = sorted(
            [name for name in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)],
            key=natural_key,
        )
        slide_texts = [texts(zf.read(name)) for name in slide_names]
        all_text = "\n".join("\n".join(parts) for parts in slide_texts)
        chart_names = sorted(
            [name for name in names if re.fullmatch(r"ppt/charts/chart\d+\.xml", name)],
            key=natural_key,
        )
        charts = {name: chart_payload(zf.read(name)) for name in chart_names}

        placeholder_patterns = [
            "请输入",
            "请在此",
            "ADD YOUR",
            "小邱",
            "大邱",
            "20XX",
            "JUNE 12th",
            "SAMPLE TITLE",
        ]
        leftovers = [item for item in placeholder_patterns if item in all_text]
        required_text = [
            "中东冲突对国际油价冲击",
            "统计方法链",
            "事件研究法",
            "CAR 核心结果",
            "13.552%",
            "3.344%",
            "结论与展望",
            "汇报结束  感谢聆听！",
        ]
        missing = [item for item in required_text if item not in all_text]

        preserved = None
        if source_deck:
            with zipfile.ZipFile(source_deck) as source_zf:
                source_names = set(source_zf.namelist())
                preserved_names = [
                    name
                    for name in names
                    if name.startswith(("ppt/slideMasters/", "ppt/theme/", "ppt/media/"))
                    and name in source_names
                    and not name.endswith("/")
                ]
                preserved = {
                    "compared_parts": len(preserved_names),
                    "byte_identical_parts": sum(
                        hashlib.sha256(zf.read(name)).digest()
                        == hashlib.sha256(source_zf.read(name)).digest()
                        for name in preserved_names
                    ),
                }

        report = {
            "deck": str(deck),
            "slide_count": len(slide_names),
            "slide_master_count": len([n for n in names if re.fullmatch(r"ppt/slideMasters/slideMaster\d+\.xml", n)]),
            "slide_layout_count": len([n for n in names if re.fullmatch(r"ppt/slideLayouts/slideLayout\d+\.xml", n)]),
            "theme_count": len([n for n in names if re.fullmatch(r"ppt/theme/theme\d+\.xml", n)]),
            "media_count": len([n for n in names if n.startswith("ppt/media/") and not n.endswith("/")]),
            "chart_count": len(chart_names),
            "notes_slide_count": len([n for n in names if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)]),
            "placeholder_leftovers": leftovers,
            "missing_required_text": missing,
            "template_part_preservation": preserved,
            "charts": charts,
        }

    (out_dir / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = ["# T3 答辩 PPT 读取校验", ""]
    for index, parts in enumerate(slide_texts, start=1):
        lines.append(f"## 第 {index} 页")
        lines.append("")
        lines.extend(part for part in parts if part.strip())
        lines.append("")
    (out_dir / "readback.md").write_text("\n".join(lines), encoding="utf-8")

    ok = len(slide_names) == 16 and not leftovers and not missing
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
