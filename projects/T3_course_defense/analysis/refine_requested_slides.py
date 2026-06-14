from __future__ import annotations

import copy
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

EMU = 9525
BLUE = "07549A"
DARK_BLUE = "063F75"
GOLD = "F5B800"
LIGHT = "F3F7FC"
PALE = "E8F1F9"
GRAY = "5B6573"
WHITE = "FFFFFF"


def natural_key(value: str):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value)]


def qn(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def shape_text(shape: ET.Element) -> str:
    return "".join(node.text or "" for node in shape.findall(".//a:t", NS)).strip()


def next_shape_id(root: ET.Element) -> int:
    ids = [int(node.get("id")) for node in root.findall(".//p:cNvPr", NS) if node.get("id", "").isdigit()]
    return max(ids, default=1) + 1


def set_geometry(shape: ET.Element, x: float, y: float, w: float, h: float) -> None:
    xfrm = shape.find("p:spPr/a:xfrm", NS)
    if xfrm is None:
        return
    off = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    off.set("x", str(round(x * EMU)))
    off.set("y", str(round(y * EMU)))
    ext.set("cx", str(round(w * EMU)))
    ext.set("cy", str(round(h * EMU)))


def set_shape_fill_line(shape: ET.Element, fill: str, line: str, width: int = 12700, rounded: bool = False) -> None:
    sppr = shape.find("p:spPr", NS)
    if sppr is None:
        return
    for child in list(sppr):
        if child.tag in {qn("a", "solidFill"), qn("a", "noFill"), qn("a", "ln")}:
            sppr.remove(child)
    geom = sppr.find("a:prstGeom", NS)
    if rounded and geom is not None:
        geom.set("prst", "roundRect")
    solid = ET.SubElement(sppr, qn("a", "solidFill"))
    ET.SubElement(solid, qn("a", "srgbClr"), {"val": fill})
    ln = ET.SubElement(sppr, qn("a", "ln"), {"w": str(width)})
    lfill = ET.SubElement(ln, qn("a", "solidFill"))
    ET.SubElement(lfill, qn("a", "srgbClr"), {"val": line})


def make_run(text: str, size: float, color: str, bold: bool) -> ET.Element:
    run = ET.Element(qn("a", "r"))
    rpr = ET.SubElement(run, qn("a", "rPr"), {"lang": "zh-CN", "sz": str(round(size * 100)), "b": "1" if bold else "0"})
    fill = ET.SubElement(rpr, qn("a", "solidFill"))
    ET.SubElement(fill, qn("a", "srgbClr"), {"val": color})
    ET.SubElement(rpr, qn("a", "latin"), {"typeface": "Aptos"})
    ET.SubElement(rpr, qn("a", "ea"), {"typeface": "Microsoft YaHei"})
    ET.SubElement(rpr, qn("a", "cs"), {"typeface": "Aptos"})
    ET.SubElement(run, qn("a", "t")).text = text
    return run


def rebuild_text(shape: ET.Element, text: str, size: float, color: str = DARK_BLUE, bold: bool = False, align: str = "l", anchor: str = "ctr") -> None:
    tx = shape.find("p:txBody", NS)
    if tx is None:
        tx = ET.SubElement(shape, qn("p", "txBody"))
    for child in list(tx):
        tx.remove(child)
    ET.SubElement(tx, qn("a", "bodyPr"), {"anchor": anchor, "lIns": "76200", "rIns": "76200", "tIns": "45720", "bIns": "45720", "wrap": "square"})
    ET.SubElement(tx, qn("a", "lstStyle"))
    for line in text.split("\n"):
        paragraph = ET.SubElement(tx, qn("a", "p"))
        ET.SubElement(paragraph, qn("a", "pPr"), {"algn": align, "fontAlgn": "base", "marL": "0", "indent": "0"})
        paragraph.append(make_run(line, size, color, bold))
        end = ET.SubElement(paragraph, qn("a", "endParaRPr"), {"lang": "zh-CN", "sz": str(round(size * 100))})
        fill = ET.SubElement(end, qn("a", "solidFill"))
        ET.SubElement(fill, qn("a", "srgbClr"), {"val": color})


def find_shape(root: ET.Element, text: str) -> ET.Element | None:
    return next((shape for shape in root.findall(".//p:sp", NS) if shape_text(shape) == text), None)


def remove_shapes(root: ET.Element, texts: set[str]) -> None:
    tree = root.find(".//p:spTree", NS)
    if tree is None:
        return
    for shape in list(tree.findall("p:sp", NS)):
        if shape_text(shape) in texts:
            tree.remove(shape)


def add_shape(root: ET.Element, x: float, y: float, w: float, h: float, text: str = "", size: float = 16, fill: str = WHITE, line: str = BLUE, color: str = DARK_BLUE, bold: bool = False, align: str = "c", preset: str = "roundRect", line_width: int = 12700, name: str = "新增形状") -> ET.Element:
    tree = root.find(".//p:spTree", NS)
    sid = next_shape_id(root)
    shape = ET.Element(qn("p", "sp"))
    nv = ET.SubElement(shape, qn("p", "nvSpPr"))
    ET.SubElement(nv, qn("p", "cNvPr"), {"id": str(sid), "name": f"{name} {sid}"})
    ET.SubElement(nv, qn("p", "cNvSpPr"))
    ET.SubElement(nv, qn("p", "nvPr"))
    sppr = ET.SubElement(shape, qn("p", "spPr"))
    xfrm = ET.SubElement(sppr, qn("a", "xfrm"))
    ET.SubElement(xfrm, qn("a", "off"), {"x": str(round(x * EMU)), "y": str(round(y * EMU))})
    ET.SubElement(xfrm, qn("a", "ext"), {"cx": str(round(w * EMU)), "cy": str(round(h * EMU))})
    geom = ET.SubElement(sppr, qn("a", "prstGeom"), {"prst": preset})
    ET.SubElement(geom, qn("a", "avLst"))
    solid = ET.SubElement(sppr, qn("a", "solidFill"))
    ET.SubElement(solid, qn("a", "srgbClr"), {"val": fill})
    ln = ET.SubElement(sppr, qn("a", "ln"), {"w": str(line_width)})
    lfill = ET.SubElement(ln, qn("a", "solidFill"))
    ET.SubElement(lfill, qn("a", "srgbClr"), {"val": line})
    rebuild_text(shape, text, size, color, bold, align)
    tree.append(shape)
    return shape


def edit_slide4(root: ET.Element) -> None:
    cards = [
        (105, "▇  ▅  ▂  ↓", "潜在减产", BLUE),
        (375, "● ── ●  ×  ●", "运输受阻", BLUE),
        (645, "t−1  →  t₀  →  t+3", "提前定价", BLUE),
        (915, "▁  ▃  ▂  ▆  ▇", "波动放大", GOLD),
    ]
    for x, chart, caption, accent in cards:
        add_shape(root, x, 150, 220, 168, "", 16, LIGHT, "B8CDE0", DARK_BLUE, False, "c")
        add_shape(root, x + 18, 174, 184, 62, chart, 25, WHITE, WHITE, accent, True, "c", "rect", 0)
        add_shape(root, x + 30, 247, 160, 42, caption, 16, PALE, PALE, DARK_BLUE, True, "c", "roundRect", 0)
    for label in ["供应", "航运", "预期", "溢价"]:
        shape = find_shape(root, label)
        if shape is not None:
            rebuild_text(shape, label, 22, DARK_BLUE, True, "c")
    for text in [
        "核设施、油田和出口终端受到威胁，市场上调潜在供应损失。",
        "霍尔木兹海峡等通道受阻预期推高运输、保险与交割成本。",
        "交易者在真实减产前提前定价，造成事件日前后价格快速调整。",
        "地缘政治不确定性提高持有与套期保值需求，放大短期波动。",
    ]:
        shape = find_shape(root, text)
        if shape is not None:
            rebuild_text(shape, text, 17, DARK_BLUE, False, "l", "t")


def edit_slide5(root: ET.Element) -> None:
    remove_shapes(root, {
        "01", "02", "03", "04", "研究目标", "分离五次冲击，比较显著性与经济幅度",
        "H2 基准", "Brent 对中东冲突的反应强于 WTI", "H1 异常",
        "重大冲突事件产生显著累计异常收益", "H3 类型", "石油设施与航运通道事件冲击更强",
    })
    add_shape(root, 155, 135, 970, 78,
              "研究问题：哪些事件造成显著油价冲击？冲击是否因基准油价与事件类型而异？",
              21, PALE, "A9C4DC", DARK_BLUE, True, "c")
    cards = [
        (100, "H1  显著冲击", "重大冲突事件发生后，WTI 与 Brent 在事件窗口内的 CAR 显著不为 0。"),
        (490, "H2  基准差异", "中东供应风险更直接作用于 Brent，其异常反应幅度预计大于 WTI。"),
        (880, "H3  事件类型", "涉及石油设施、出口终端或霍尔木兹海峡的事件，其 CAR 绝对值更大、显著性更强。"),
    ]
    for x, title, body in cards:
        add_shape(root, x, 265, 300, 72, title, 20, BLUE, BLUE, WHITE, True, "c")
        add_shape(root, x, 337, 300, 245, body, 17, WHITE, "9AB9D3", DARK_BLUE, False, "l")


def edit_slide8(root: ET.Element) -> None:
    positions = {"事件": 165, "CAR": 420, "ITS": 675, "诊断": 930}
    for text, x in positions.items():
        shape = find_shape(root, text)
        if shape is not None:
            set_geometry(shape, x, 318, 180, 48)
            rebuild_text(shape, text, 19, WHITE, True, "c")
    remove_shapes(root, {"完整分析流程", "外部事实选取事件 → 市场模型估计正常收益 → AR 与 CAR → 显著性检验 → ITS 分离水平/趋势 → DW、BP、Newey-West 与结构断点"})
    add_shape(root, 430, 430, 420, 48, "六步识别路径", 20, WHITE, WHITE, DARK_BLUE, True, "c", "rect", 0)
    steps = ["1 事件核验", "2 正常收益", "3 AR / CAR", "4 显著性", "5 ITS 分离", "6 诊断断点"]
    xs = [70, 265, 460, 655, 850, 1045]
    for i, (x, text) in enumerate(zip(xs, steps)):
        add_shape(root, x, 505, 150, 64, text, 14.5, BLUE if i % 2 == 0 else "6D7782", BLUE if i % 2 == 0 else "6D7782", WHITE, True, "c")
        if i < len(steps) - 1:
            add_shape(root, x + 158, 521, 28, 32, "", 10, GOLD, GOLD, GOLD, False, "c", "chevron", 0)


def edit_slide9(root: ET.Element) -> None:
    add_shape(root, 115, 120, 1050, 58,
              "事件研究法以事件日为中心，先估计“无事件情形”的正常收益，再检验实际收益偏离是否显著。",
              15.5, PALE, PALE, DARK_BLUE, False, "l", "roundRect", 0)
    replacements = {
        "Rᵢ,ₜ = αᵢ + βᵢRₘ,ₜ + εᵢ,ₜ估计窗：[-120,-21]":
            "Rᵢ,ₜ = αᵢ + βᵢRₘ,ₜ + εᵢ,ₜ\n估计窗口：[-120,-21]\n作用：预测无事件时的正常收益",
        "ARᵢ,ₜ = Rᵢ,ₜ − Ê(Rᵢ,ₜ)CAR = Σ ARᵢ,ₜ":
            "ARᵢ,ₜ = Rᵢ,ₜ − Ê(Rᵢ,ₜ)\nCAR(τ₁,τ₂) = Σ ARᵢ,ₜ\n作用：累积事件窗口内的异常反应",
        "t = CAR/(σ̂AR√L)窗口：[-1,+1]、[0,+3]、[0,+5]\n补充 BH-FDR 与 Bonferroni":
            "t = CAR / (σ̂AR √L)\nL：事件窗口交易日数\n窗口：[-1,+1]、[0,+3]、[0,+5]\n补充 BH-FDR 与 Bonferroni",
    }
    for old, new in replacements.items():
        shape = find_shape(root, old)
        if shape is not None:
            rebuild_text(shape, new, 15.5, WHITE, False, "l")
    for title in ["市场模型", "AR 与 CAR", "显著性"]:
        shape = find_shape(root, title)
        if shape is not None:
            rebuild_text(shape, title, 22, WHITE, True, "c")
    add_shape(root, 120, 585, 1040, 70,
              "变量对应：Rᵢ,ₜ=目标油价收益率；Rₘ,ₜ=市场因子收益率；αᵢ=平均水平；βᵢ=联动敏感度；εᵢ,ₜ=随机扰动；L=窗口长度。\n本研究中 WTI 与 Brent 互为市场因子，因此 CAR 表示相对异常反应。",
              12.8, LIGHT, "9AB9D3", DARK_BLUE, False, "l")


def edit_slide10(root: ET.Element) -> None:
    add_shape(root, 115, 125, 1050, 58,
              "ITS 负责估计冲击如何改变收益率路径；DW、BP 与 Newey-West 用于判断推断是否可靠。",
              15.5, PALE, PALE, DARK_BLUE, False, "l", "roundRect", 0)
    replacements = {
        "rₜ = β₀ + β₁timeₜ+ β₂postₜ+ β₃time_afterₜ + εₜβ₂：即时冲击β₃：趋势变化":
            "回答：事件是否改变收益率路径？\n\nrₜ = β₀ + β₁timeₜ + β₂postₜ\n    + β₃time_afterₜ + εₜ\n\nβ₂：即时水平冲击\nβ₃：事件后的趋势变化",
        "Durbin-Watson检查残差一阶自相关接近 2 表示相关性较弱":
            "检查：残差是否存在一阶自相关\n\nDW ≈ 2：相关性较弱\n明显偏离 2：OLS 标准误可能失真",
        "Breusch-Pagan检验残差方差是否稳定p < 0.05 提示异方差":
            "检查：残差方差是否恒定\n\np < 0.05：存在异方差\n需要使用稳健标准误进行推断",
        "Newey-West 修正标准误RSS/BIC 网格搜索近似 Bai-Perron比较断点与事件日期":
            "修正：同时容许异方差与自相关\n\n断点：RSS/BIC 搜索结构变化\n验证：统计断点是否靠近事件日",
    }
    for old, new in replacements.items():
        shape = find_shape(root, old)
        if shape is not None:
            rebuild_text(shape, new, 14.5, DARK_BLUE, False, "l", "t")
    for title in ["ITS", "DW", "BP", "NW"]:
        shape = find_shape(root, title)
        if shape is not None:
            rebuild_text(shape, title, 20, WHITE, True, "c")


def edit_slide12(root: ET.Element) -> None:
    body_texts = [
        "均值 0.081%；偏度 -0.888；峰度 9.855。负偏与高峰度表明下行尾部风险突出。",
        "均值 0.080%；偏度 -0.547；峰度 8.391。Brent 同样呈现明显高峰厚尾。",
        "两种基准油价高度联动，但对中东供应风险的敏感度和反应幅度并不完全一致。",
    ]
    for text in body_texts:
        shape = find_shape(root, text)
        if shape is not None:
            set_shape_fill_line(shape, LIGHT, "9AB9D3", 15875, True)
            rebuild_text(shape, text, 16, DARK_BLUE, False, "l")
    for label in ["WTI 波动", "Brent σ", "相关系数"]:
        shape = find_shape(root, label)
        if shape is not None:
            set_shape_fill_line(shape, PALE, PALE, 0, True)
            rebuild_text(shape, label, 15, DARK_BLUE, True, "c")


def edit_chart_title(chart_path: Path) -> None:
    root = ET.parse(chart_path).getroot()
    title = root.find(".//c:title", NS)
    if title is None:
        return
    nodes = title.findall(".//a:t", NS)
    if nodes:
        nodes[0].text = "五个事件的 CAR（主窗口 [0,+3]，%）"
        for node in nodes[1:]:
            node.text = ""
    for rpr in title.findall(".//a:rPr", NS):
        rpr.set("sz", "1800")
        rpr.set("b", "1")
        fill = rpr.find("a:solidFill", NS)
        if fill is None:
            fill = ET.SubElement(rpr, qn("a", "solidFill"))
        for child in list(fill):
            fill.remove(child)
        ET.SubElement(fill, qn("a", "srgbClr"), {"val": DARK_BLUE})
    ET.ElementTree(root).write(chart_path, encoding="utf-8", xml_declaration=True)


def main() -> None:
    source = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        with zipfile.ZipFile(source) as zf:
            zf.extractall(temp)
        slides = sorted((temp / "ppt" / "slides").glob("slide*.xml"), key=lambda p: natural_key(p.name))
        editors = {4: edit_slide4, 5: edit_slide5, 8: edit_slide8, 9: edit_slide9, 10: edit_slide10, 12: edit_slide12}
        for index, editor in editors.items():
            path = slides[index - 1]
            root = ET.parse(path).getroot()
            editor(root)
            ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
        edit_chart_title(temp / "ppt" / "charts" / "chart4.xml")
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in temp.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(temp).as_posix())
    print(output)


if __name__ == "__main__":
    main()
