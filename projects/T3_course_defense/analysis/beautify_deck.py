from __future__ import annotations

import copy
import posixpath
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix if prefix != "pr" else "", uri)

EMU_PER_PX = 9525


def natural_key(value: str):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", value)]


def shape_text(shape: ET.Element) -> str:
    return "".join(node.text or "" for node in shape.findall(".//a:t", NS)).strip()


def set_font(run_props: ET.Element, size_pt: float | None = None, bold: bool | None = None) -> None:
    if size_pt is not None:
        run_props.set("sz", str(round(size_pt * 100)))
    if bold is not None:
        run_props.set("b", "1" if bold else "0")
    run_props.set("lang", "zh-CN")
    for tag, face in (("latin", "Aptos"), ("ea", "Microsoft YaHei"), ("cs", "Aptos")):
        child = run_props.find(f"a:{tag}", NS)
        if child is None:
            child = ET.SubElement(run_props, f"{{{NS['a']}}}{tag}")
        child.set("typeface", face)


def style_shape(shape: ET.Element, size_pt: float | None, bold: bool | None, align: str = "l") -> None:
    tx_body = shape.find("p:txBody", NS)
    if tx_body is None:
        return
    body_pr = tx_body.find("a:bodyPr", NS)
    if body_pr is not None:
        body_pr.set("anchor", "ctr")
        body_pr.set("lIns", "76200")
        body_pr.set("rIns", "76200")
        body_pr.set("tIns", "45720")
        body_pr.set("bIns", "45720")
    for paragraph in tx_body.findall("a:p", NS):
        ppr = paragraph.find("a:pPr", NS)
        if ppr is None:
            ppr = ET.Element(f"{{{NS['a']}}}pPr")
            paragraph.insert(0, ppr)
        ppr.set("algn", align)
        ppr.set("fontAlgn", "base")
        ppr.set("marL", "0")
        ppr.set("indent", "0")
        for run in paragraph.findall("a:r", NS):
            rpr = run.find("a:rPr", NS)
            if rpr is None:
                rpr = ET.Element(f"{{{NS['a']}}}rPr")
                run.insert(0, rpr)
            set_font(rpr, size_pt, bold)
        end = paragraph.find("a:endParaRPr", NS)
        if end is None:
            end = ET.SubElement(paragraph, f"{{{NS['a']}}}endParaRPr")
        set_font(end, size_pt, bold)


def set_geometry(shape: ET.Element, x_px=None, y_px=None, w_px=None, h_px=None) -> None:
    xfrm = shape.find("p:spPr/a:xfrm", NS)
    if xfrm is None:
        return
    off = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    if off is not None:
        if x_px is not None:
            off.set("x", str(round(x_px * EMU_PER_PX)))
        if y_px is not None:
            off.set("y", str(round(y_px * EMU_PER_PX)))
    if ext is not None:
        if w_px is not None:
            ext.set("cx", str(round(w_px * EMU_PER_PX)))
        if h_px is not None:
            ext.set("cy", str(round(h_px * EMU_PER_PX)))


def style_by_text(root: ET.Element, rules: list[tuple[str, float, bool, str]]) -> None:
    for shape in root.findall(".//p:sp", NS):
        text = shape_text(shape)
        for exact, size, bold, align in rules:
            if text == exact:
                style_shape(shape, size, bold, align)
                break


def remove_people(root: ET.Element, rels_root: ET.Element) -> None:
    rel_map = {
        rel.attrib["Id"]: posixpath.basename(rel.attrib.get("Target", ""))
        for rel in rels_root.findall("pr:Relationship", NS)
    }
    sp_tree = root.find(".//p:spTree", NS)
    if sp_tree is None:
        return
    for pic in list(sp_tree.findall("p:pic", NS)):
        blip = pic.find(".//a:blip", NS)
        rid = blip.attrib.get(f"{{{NS['r']}}}embed") if blip is not None else None
        if rel_map.get(rid) in {"image15.jpeg", "image16.jpeg"}:
            sp_tree.remove(pic)


def style_slide(index: int, root: ET.Element) -> None:
    title_shapes = []
    for shape in root.findall(".//p:sp", NS):
        text = shape_text(shape)
        xfrm = shape.find("p:spPr/a:xfrm", NS)
        off = xfrm.find("a:off", NS) if xfrm is not None else None
        y = int(off.attrib.get("y", 99999999)) if off is not None else 99999999
        if text and y < 900000 and text not in {"BEIHANG UNIVERSITY", "目 录", "CONTENTS"}:
            title_shapes.append(shape)
    if index not in {1, 2, 3, 7, 11, 16}:
        for shape in title_shapes:
            text = shape_text(shape)
            if text not in {"2026.06"}:
                style_shape(shape, 28, True, "l")

    common_small = ["2026.06", "BEIHANG UNIVERSITY"]
    style_by_text(root, [(t, 9, False, "c") for t in common_small])

    rules: dict[int, list[tuple[str, float, bool, str]]] = {
        1: [
            ("中东冲突对国际油价冲击事件研究法与回归分析", 34, True, "c"),
            ("数理统计课程作业答辩", 18, False, "c"),
            ("汇报人：XXX", 15, False, "c"),
            ("指导教师：XXX", 15, False, "c"),
            ("2026年6月12日", 15, False, "c"),
        ],
        2: [
            ("研究背景与问题", 20, True, "l"), ("统计方法与设计", 20, True, "l"),
            ("实证结果与解释", 20, True, "l"), ("结论、局限与展望", 20, True, "l"),
            ("BACKGROUND & QUESTIONS", 10, False, "l"), ("METHODS & DESIGN", 10, False, "l"),
            ("EMPIRICAL RESULTS", 10, False, "l"), ("CONCLUSION & OUTLOOK", 10, False, "l"),
        ],
        3: [("研究背景与问题", 36, True, "c"), ("冲突升级如何改变石油供应预期、航运安全与风险溢价？", 17, False, "c")],
        4: [
            ("供应", 19, True, "c"), ("航运", 19, True, "c"), ("预期", 19, True, "c"), ("溢价", 19, True, "c"),
            ("核设施、油田和出口终端受到威胁，市场上调潜在供应损失。", 15, False, "l"),
            ("霍尔木兹海峡等通道受阻预期推高运输、保险与交割成本。", 15, False, "l"),
            ("交易者在真实减产前提前定价，造成事件日前后价格快速调整。", 15, False, "l"),
            ("地缘政治不确定性提高持有与套期保值需求，放大短期波动。", 15, False, "l"),
        ],
        5: [
            ("研究目标", 17, True, "c"), ("H1 异常", 17, True, "c"), ("H2 基准", 17, True, "c"), ("H3 类型", 17, True, "c"),
            ("分离五次冲击，比较显著性与经济幅度", 15, False, "c"),
            ("重大冲突事件产生显著累计异常收益", 15, False, "c"),
            ("Brent 对中东冲突的反应强于 WTI", 15, False, "c"),
            ("石油设施与航运通道事件冲击更强", 15, False, "c"),
        ],
        6: [],
        7: [("统计方法与研究设计", 36, True, "c"), ("事件研究识别短期异常反应，ITS 与断点检验验证动态变化", 17, False, "c")],
        8: [("事件", 16, True, "c"), ("CAR", 16, True, "c"), ("ITS", 16, True, "c"), ("诊断", 16, True, "c"), ("完整分析流程", 20, True, "c")],
        9: [("正常收益模型", 20, True, "c"), ("异常收益与 CAR", 20, True, "c"), ("检验与窗口", 20, True, "c")],
        10: [("ITS", 17, True, "c"), ("DW", 17, True, "c"), ("BP", 17, True, "c"), ("NW", 17, True, "c")],
        11: [("实证结果与解释", 36, True, "c"), ("统计显著性、经济幅度与冲击机制需要结合解读", 17, False, "c")],
        12: [("2.901%", 42, True, "c"), ("2.984%", 42, True, "c"), ("0.845", 42, True, "c"),
             ("WTI 波动", 15, True, "c"), ("Brent σ", 15, True, "c"), ("相关系数", 15, True, "c")],
        13: [],
        14: [("ITS 核心发现", 18, True, "l"), ("诊断与断点", 18, True, "l")],
        15: [("主要结论", 18, True, "l"), ("局限与展望", 18, True, "l")],
        16: [("汇报结束  感谢聆听！", 42, True, "c"), ("汇报人：XXX", 15, False, "c"), ("指导教师：XXX", 15, False, "c"), ("2026年6月12日", 15, False, "c")],
    }
    style_by_text(root, rules.get(index, []))

    # Common body hierarchy for the dense academic slides.
    if index in {6, 14, 15}:
        for shape in root.findall(".//p:sp", NS):
            text = shape_text(shape)
            if text and len(text) > 18 and "BEIHANG" not in text:
                style_shape(shape, 14.5, False, "l")
    elif index in {8, 9, 10, 13}:
        for shape in root.findall(".//p:sp", NS):
            text = shape_text(shape)
            if text and len(text) > 22 and "BEIHANG" not in text:
                style_shape(shape, 14.5, False, "l" if index != 9 else "c")


def main() -> None:
    source = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        with zipfile.ZipFile(source) as zf:
            zf.extractall(temp)
        slide_paths = sorted((temp / "ppt" / "slides").glob("slide*.xml"), key=lambda p: natural_key(p.name))
        for index, slide_path in enumerate(slide_paths, start=1):
            rel_path = slide_path.parent / "_rels" / f"{slide_path.name}.rels"
            root = ET.parse(slide_path).getroot()
            rels_root = ET.parse(rel_path).getroot()
            if index == 4:
                remove_people(root, rels_root)
            style_slide(index, root)
            ET.ElementTree(root).write(slide_path, encoding="utf-8", xml_declaration=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in temp.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(temp).as_posix())
    print(output)


if __name__ == "__main__":
    main()
