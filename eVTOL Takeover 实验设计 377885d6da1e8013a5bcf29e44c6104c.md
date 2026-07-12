# eVTOL Takeover 实验设计

## 自变量：

1. **不同模态的接管请求（听觉，视觉，多模态(听觉+视觉), within**
2. **能见度（正常，大雾, within**
3. **是否进行接管培训（通用/通用+接管培训, between**

插两次空白试验，第一次和中间的一次（共八次实验）

共需:3*2*2*2=24人 *2 = 48人

### **训练设计原则:**

接管训练与常规飞行训练的根本区别在于：训练目标不是"如何飞"，而是**"如何在被动监控状态下，瞬间切入并稳定一架正在下降的飞行器"**。

| **训练模块** | **针对的接管难点** | **核心训练内容** |
| --- | --- | --- |
| ① 接管启动与态势重建 | 监控→操控的"控制权交接"延迟 | 失效提示识别、双手回到操纵杆/油门的标准动作、3 秒内完成态势扫描 |
| ② HCM 速度控制再适应 | HCM 下杆量指令"地速"而非姿态，新手易过度修正 | 接管瞬间的小幅、增量式输入训练，抑制 over-correction |
| ③ 梯形进近程序（LAP）接管化 | 失效常发生在阶梯下降中途 | 在任意阶梯段被"丢回"手动时，如何续接 LAP 的分级高度调整 |
| ④ 地面效应与精准落点 | 近地面增升、漂浮，落点偏移 | 控制下降率、G 值管理，在 TLOF 中心稳定接地 |
| ⑤ 低能见度接管 | 视觉线索缺失下的接管 | 仪表主导的接管决策、IFR→VFR 切换时机 |
1. 自主飞行时双手应该置于何处（握住操作杆不动？）是否有要求？都放在双腿上。
2. 接管发生时机由场景来定义，如前方有障碍物（大楼），强制手动接管。所以是否接管发生在下降阶段还是平飞阶段可以不用定义？**前方障碍物，系统内部故障，风切变**
3. 常规飞行训练会包含IFR和VFR的内容（不强制要求），低能见度条件下接管是否不用强制要求参与者采用IFR/VFR？最后还可以根据实验结果来探究参与者是采用IFR还是VFR。VFR
4. 如何实现接管？绿野仙踪还是采用软件真实操作接管。

## **因变量：**

- **接管质量。飞行绩效**：XTE（均值/RMSE/SD）、Bank（绝对均值/SD）、Pitch（绝对均值/SD）、垂直速度、接地 G 值、降落成功率。
- **客观负荷。生理状态**：EEG 区域 ATBR（Frontal/Central 重点）、HRV（SDNN/RMSSD/LF/HF）、EDA（SCL/SCR）、RESP（RR/RD）。（负荷）
- **行为与视觉。**单目视觉注视序列、首次锁定目标时间、对辅助提示的采纳率、接管/否决次数。（研究降落时IFR/VFR的比例）
    
    ### 未来工作：eVTOL 专用 IFR 仪表与注视分析
    
    这是一条清晰的延伸路径：
    
    - 在 IFR 主导场景下，**用眼动追踪**记录飞行员在仪表上的注视分配（哪些信息被高频扫视）；
    - 由此反推**eVTOL 降落专用仪表**应优先呈现的信息（如阶梯高度余量、落点偏差、下降率/G 值）；
    - 这与原论文参考文献中的飞行员注视/扫视研究 [67][72] 形成方法学衔接。
- **主观负荷,ground truth。量表**：NASA-TLX、Van Der Laan 接受度量表、信任量表（Trust in Automation）
- **接管反应时间: 从警报到人接管控制的时延**

---

# 详细实验方案

1. 停机坪：ZKMZN,楼顶停机坪
2. 天气：正常；大雨（已预设，能见度要低）
3. 接管请求模态：听觉；视觉；多模态（听觉+视觉），解释接管原因：”请接管,xxx“。车辆对于L3接管的提前量要求是4/5s？10s
4. 大约5分钟的基本操作培训+复习5分钟；大约5分钟的基本操作培训+5分钟的接管操作培训

---

# 实验安排

1. Yimin Wang,制作被试招募海报，招募被试，准备基本的人口统计学信息问卷，人格问卷，收集数据，邀请函。负责eVTOL培训+接管培训。**人口统计学问卷需要加一个驾驶里程调查**

[314238677_按分数_TIPI量表_34_34.xlsx](eVTOL%20Takeover%20%E5%AE%9E%E9%AA%8C%E8%AE%BE%E8%AE%A1/314238677_%E6%8C%89%E5%88%86%E6%95%B0_TIPI%E9%87%8F%E8%A1%A8_34_34.xlsx)

[eVTOL飞行状态监测被试招募_302679844.docx](eVTOL%20Takeover%20%E5%AE%9E%E9%AA%8C%E8%AE%BE%E8%AE%A1/eVTOL%E9%A3%9E%E8%A1%8C%E7%8A%B6%E6%80%81%E7%9B%91%E6%B5%8B%E8%A2%AB%E8%AF%95%E6%8B%9B%E5%8B%9F_302679844.docx)

[p05被试费-志愿者邀请函_-_副本(1).docx](eVTOL%20Takeover%20%E5%AE%9E%E9%AA%8C%E8%AE%BE%E8%AE%A1/p05%E8%A2%AB%E8%AF%95%E8%B4%B9-%E5%BF%97%E6%84%BF%E8%80%85%E9%82%80%E8%AF%B7%E5%87%BD_-_%E5%89%AF%E6%9C%AC(1).docx)

[招募海报.pptx](eVTOL%20Takeover%20%E5%AE%9E%E9%AA%8C%E8%AE%BE%E8%AE%A1/%E6%8B%9B%E5%8B%9F%E6%B5%B7%E6%8A%A5.pptx)

[eVTOL飞行状态监测被试招募_302679844.docx](eVTOL%20Takeover%20%E5%AE%9E%E9%AA%8C%E8%AE%BE%E8%AE%A1/eVTOL%E9%A3%9E%E8%A1%8C%E7%8A%B6%E6%80%81%E7%9B%91%E6%B5%8B%E8%A2%AB%E8%AF%95%E6%8B%9B%E5%8B%9F_302679844%201.docx)

1. Zhuohao Wu, 准备NASA问卷，收集数据。按照拉丁方，将每名被试的详细实验安排表格打印出来。负责收集生理数据：EEG，ECG，EDA,RESP。

[https://wcnb3pif9p8w.feishu.cn/docx/Y3oZdpc3poLFEZx0ozpc2zejnxe?from=from_copylink](https://wcnb3pif9p8w.feishu.cn/docx/Y3oZdpc3poLFEZx0ozpc2zejnxe?from=from_copylink)

[eVTOL_拉丁方实验安排表.xlsx](eVTOL%20Takeover%20%E5%AE%9E%E9%AA%8C%E8%AE%BE%E8%AE%A1/eVTOL_%E6%8B%89%E4%B8%81%E6%96%B9%E5%AE%9E%E9%AA%8C%E5%AE%89%E6%8E%92%E8%A1%A8.xlsx)

![image.png](eVTOL%20Takeover%20%E5%AE%9E%E9%AA%8C%E8%AE%BE%E8%AE%A1/image.png)

1. Xiang Chang, 准备接管模态的工具。听觉，视觉
2. Chenglin Liu,准备普通培训方案与接管培训方案，准备任务要求，准备自动驾驶接管软件。

[eVTOL飞行员飞培训与负荷研究实验方案 0309(1).docx](eVTOL%20Takeover%20%E5%AE%9E%E9%AA%8C%E8%AE%BE%E8%AE%A1/eVTOL%E9%A3%9E%E8%A1%8C%E5%91%98%E9%A3%9E%E5%9F%B9%E8%AE%AD%E4%B8%8E%E8%B4%9F%E8%8D%B7%E7%A0%94%E7%A9%B6%E5%AE%9E%E9%AA%8C%E6%96%B9%E6%A1%88_0309(1).docx)

[eVTOL基础飞行训练方案(2).docx](eVTOL%20Takeover%20%E5%AE%9E%E9%AA%8C%E8%AE%BE%E8%AE%A1/eVTOL%E5%9F%BA%E7%A1%80%E9%A3%9E%E8%A1%8C%E8%AE%AD%E7%BB%83%E6%96%B9%E6%A1%88(2).docx)

[副本eVTOL 进阶培训方案new0410_副本.docx](eVTOL%20Takeover%20%E5%AE%9E%E9%AA%8C%E8%AE%BE%E8%AE%A1/%E5%89%AF%E6%9C%ACeVTOL_%E8%BF%9B%E9%98%B6%E5%9F%B9%E8%AE%AD%E6%96%B9%E6%A1%88new0410_%E5%89%AF%E6%9C%AC.docx)

[副本任务要求(1)(1).docx](eVTOL%20Takeover%20%E5%AE%9E%E9%AA%8C%E8%AE%BE%E8%AE%A1/%E5%89%AF%E6%9C%AC%E4%BB%BB%E5%8A%A1%E8%A6%81%E6%B1%82(1)(1).docx)