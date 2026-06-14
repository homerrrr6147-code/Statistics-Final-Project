# T3 LaTeX 课程论文

## 生成统计表

在项目根目录运行：

```powershell
python src\t3_oil_event_study.py
python paper\build_tables.py
```

## 编译论文

进入 `paper` 目录后运行：

```powershell
latexmk -xelatex -interaction=nonstopmode -halt-on-error -jobname=T3_course_paper main.tex
```

本机 `latexmk` 会根据 `biblatex` 配置自动调用 Biber，不需要额外传入 `-use-biber`。

最终文件为 `paper/T3_course_paper.pdf`。提交前请在 `main.tex` 封面处填写姓名、学号和任课教师。
