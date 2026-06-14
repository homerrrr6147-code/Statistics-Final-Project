# T3 答辩 PPT 读取校验

## 第 1 页

汇报人：XXX
指导教师：XXX
2026年6月12日
中东冲突对国际油价冲击
事件研究法与回归分析
数理统计课程作业答辩
BEIHANG UNIVERSITY

## 第 2 页

CONTENTS
目 录
01
02
03
04
研究背景与问题
BACKGROUND & QUESTIONS
统计方法与设计
METHODS & DESIGN
实证结果与解释
EMPIRICAL RESULTS
结论、局限与展望
CONCLUSION & OUTLOOK
BEIHANG UNIVERSITY

## 第 3 页

01
研究背景与问题
冲突升级如何改变石油供应预期、航运安全与风险溢价？
BEIHANG UNIVERSITY

## 第 4 页

冲突传导机制
2026.06
BEIHANG UNIVERSITY
供应
核设施、油田和出口终端受到威胁，市场上调潜在供应损失。
航运
霍尔木兹海峡等通道受阻预期推高运输、保险与交割成本。
预期
交易者在真实减产前提前定价，造成事件日前后价格快速调整。
溢价
地缘政治不确定性提高持有与套期保值需求，放大短期波动。

## 第 5 页

研究问题与三项假设
2026.06
BEIHANG UNIVERSITY
01
02
03
04
研究目标
分离五次冲击，比较显著性与经济幅度
H2 基准
Brent 对中东冲突的反应强于 WTI
H1 异常
重大冲突事件产生显著累计异常收益
H3 类型
石油设施与航运通道事件冲击更强

## 第 6 页

数据与样本
2026.06
BEIHANG UNIVERSITY
FRED：WTI（DCOILWTICO）与 Brent（DCOILBRENTEU）日度现货价
数据与变量
收益率：rₜ = ln(Pₜ) − ln(Pₜ₋₁)，共 345 个交易日
ACLED：六个目标国家的周度事件数与死亡人数，仅作背景验证
1
2
3
样本区间：2025-01-01 至 2026-06-01
样本设计
五个事件：E1–E5，覆盖核设施、联合打击、出口设施与海峡风险
事件日映射至最近交易日；事件选择不使用事后油价波动
1
2
3

## 第 7 页

02
统计方法与研究设计
事件研究识别短期异常反应，ITS 与断点检验验证动态变化
BEIHANG UNIVERSITY

## 第 8 页

统计方法链
2026.06
BEIHANG UNIVERSITY
事件
CAR
ITS
诊断
外部事实选取事件 → 市场模型估计正常收益 → AR 与 CAR → 显著性检验 → ITS 分离水平/趋势 → DW、BP、Newey-West 与结构断点
完整分析流程

## 第 9 页

事件研究法
2026.06
BEIHANG UNIVERSITY
市场模型
AR 与 CAR
t = CAR/(σ̂AR√L)
窗口：[-1,+1]、[0,+3]、[0,+5]
补充 BH-FDR 与 Bonferroni
显著性
ARᵢ,ₜ = Rᵢ,ₜ − Ê(Rᵢ,ₜ)
CAR = Σ ARᵢ,ₜ
Rᵢ,ₜ = αᵢ + βᵢRₘ,ₜ + εᵢ,ₜ
估计窗：[-120,-21]

## 第 10 页

ITS 与诊断
2026.06
BEIHANG UNIVERSITY
ITS
DW
BP
NW
rₜ = β₀ + β₁timeₜ
+ β₂postₜ
+ β₃time_afterₜ + εₜ
β₂：即时冲击
β₃：趋势变化
Durbin-Watson
检查残差一阶自相关
接近 2 表示相关性较弱
Breusch-Pagan
检验残差方差是否稳定
p < 0.05 提示异方差
Newey-West 修正标准误
RSS/BIC 网格搜索近似 Bai-Perron
比较断点与事件日期

## 第 11 页

03
实证结果与解释
统计显著性、经济幅度与冲击机制需要结合解读
BEIHANG UNIVERSITY

## 第 12 页

收益率特征
2026.06
BEIHANG UNIVERSITY
2.901%
2.984%
0.845
WTI 波动
Brent σ
相关系数
均值 0.080%；偏度 -0.547；峰度 8.391。Brent 同样呈现明显高峰厚尾。
均值 0.081%；偏度 -0.888；峰度 9.855。负偏与高峰度表明下行尾部风险突出。
两种基准油价高度联动，但对中东供应风险的敏感度和反应幅度并不完全一致。

## 第 13 页

CAR 核心结果
2026.06
BEIHANG UNIVERSITY
E4 冲击最强：Brent CAR 为 13.552%，WTI 相对 CAR 为 -10.198%，经 BH-FDR 与 Bonferroni 修正后仍显著。E2、E3 仅在原始检验中呈边际显著，修正后不稳健。

## 第 14 页

ITS 与断点
2026.06
BEIHANG UNIVERSITY
E3 Brent 即时水平冲击：+3.344%，NW p = 0.0109
ITS 核心发现
E4 WTI 相对即时冲击：-3.082%，NW p = 0.0459
其余事件的即时或趋势变化多数缺乏稳健显著性
1
2
3
DW 多数接近 2，残差一阶自相关总体有限
诊断与断点
部分 BP 检验显著，因此使用 Newey-West 修正推断
WTI/Brent 断点集中于 2026-02-27 至 03-02，与 E3 高度重合
1
2
3

## 第 15 页

结论与展望
2026.06
BEIHANG UNIVERSITY
事件冲击并非普遍显著，E4 是主窗口中最稳健、经济幅度最大的事件
主要结论
Brent 对中东供应风险反应更直接，支持基准油价敏感度差异
CAR、ITS 与断点结果共同支持事件影响具有类型和时点异质性
1
2
3
WTI 与 Brent 互为市场因子，CAR 是相对异常反应而非绝对因果效应
局限与展望
ACLED 为周度汇总，不能替代 actor、地点和 notes 层面的逐事件数据
后续引入独立商品指数、汇率与库存控制，并扩展联合事件模型
1
2
3

## 第 16 页

汇报人：XXX
指导教师：XXX
2026年6月12日
BEIHANG UNIVERSITY
汇报结束  感谢聆听！
