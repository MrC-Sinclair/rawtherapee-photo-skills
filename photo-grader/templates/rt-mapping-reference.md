# LR→RT 映射差异（grade.py 私有逻辑）

> 以下映射由 `grade.py` 的 `rt_map_*()` 函数实现。Curator 输出 Lightroom 标准参数，引擎自动转换。
> RT PP3 使用 (section, key) 格式，键名与 RawTherapee 实际格式一致。

| LR 参数            | RT PP3 Section.Key                                        | 映射行为                                             |
| ------------------ | --------------------------------------------------------- | ---------------------------------------------------- |
| exposure           | Exposure.Compensation                                     | x2.0 放大；负曝光同时提黑位 (Exposure.Black)         |
| contrast           | Exposure.Contrast                                         | x0.8 缩放（RT 对比度更激进）                         |
| highlights (+)     | Exposure.HighlightCompr                                   | 正值 → HighlightCompr                                |
| highlights (-)     | HLRecovery.Enabled/Method/Hlbl                            | 负值 → 高光恢复 (Coloropp 方法)                      |
| shadows (+)        | Exposure.ShadowCompr                                      | 正值 → ShadowCompr                                   |
| shadows (-)        | Shadows & Highlights.Enabled/Shadows                      | 负值 → 阴影恢复                                      |
| temp_offset        | _(不直接映射)_                                            | RT 需要绝对色温，禁止写成 Temperature=5.0 这类偏移值 |
| temperature_kelvin | White Balance.Temperature                                 | 绝对色温，安全范围 2000~25000K                       |
| green              | White Balance.Green                                       | 绝对 Green 倍率，安全范围 0.5~2.0                    |
| tint_offset        | White Balance.Green                                       | 未设置 green 时，1.0 + tint × 0.005 并钳位到 0.5~2.0 |
| vibrance           | Vibrance.Enabled/Pastels                                  | x0.9 缩放                                            |
| saturation         | Vibrance.Enabled/Saturated                                | x0.7 缩放                                            |
| tone_curve         | Exposure.Curve/CurveMode                                  | 10 点 CubicSpline 曲线                               |
| hsl (8 channels)   | HSV Equalizer.Enabled/HCurve/SCurve/VCurve                | 通道映射到色相环位置（红 0°/橙 30°/黄 60°/绿 120°/青 180°/蓝 240°/紫 270°/品红 300°），生成 FlatCurve 曲线（类型 1；恒等线 y=0.5） |
| color_grading      | ColorToning.Enabled/Method=Splitco/Redlow·Greenlow·Bluelow·Redmed·Greenmed·Bluemed·Redhigh·Greenhigh·Bluehigh + Strength | 色相+饱和 → 每区 RGB 滑块（hsv_to_rgb(h,1,1)×sat）；Strength=100 使染色强度 = saturation/200 |
| sharpen            | Sharpening.Enabled/Method/DeconvRadius/DeconvAmount       | RL Deconvolution；amount x1.5，radius × 0.75         |
| noise_reduction    | Directional Pyramid Denoising.Enabled/Luma/Chroma/Ldetail | Lab 方法；gamma 1.4                                  |
| vignette_amount    | Vignetting Correction.Amount/Radius/Strength              | abs(x) × 1.5                                         |
| grain_amount       | _(RT 无内置颗粒模块)_                                     | 记录为注释；无法映射到 RT                            |

### RT Section 与 PP3 键名对照

| RT Section                      | 示例键名                                                          | 说明                |
| ------------------------------- | ----------------------------------------------------------------- | ------------------- |
| [Version]                       | AppVersion, Version                                               | RT 版本标识         |
| [Exposure]                      | Compensation, Black, Contrast, HighlightCompr, ShadowCompr, Curve | 曝光与对比度        |
| [HLRecovery]                    | Enabled, Method, Hlbl                                             | 高光恢复            |
| [White Balance]                 | Temperature, Green, Equal                                         | 白平衡              |
| [Vibrance]                      | Enabled, Pastels, Saturated                                       | 自然饱和度          |
| [Color Management]              | ToneCurve, OutputBPC                                              | 色彩管理            |
| [HSV Equalizer]                 | HCurve, SCurve, VCurve（真键，非 HueCurve/SatCurve/ValCurve）      | HSV 曲线调整        |
| [ColorToning]                   | Method=Splitco, Redlow..Bluehigh, Strength, Balance               | 色调分离            |
| [Sharpening]                    | Method, DeconvRadius, DeconvAmount                                | 锐化（RL 反卷积）   |
| [Directional Pyramid Denoising] | Enabled, Luma, Chroma, Ldetail                                    | 降噪（方向金字塔）  |
| [Vignetting Correction]         | Amount, Radius, Strength                                          | 暗角校正            |
| [Shadows & Highlights]          | Enabled, Shadows                                                  | 阴影/高光恢复       |
| [LensProfile]                   | LcMode, UseDistortion                                             | 镜头校正（lensfun） |
| [RAW]                           | HotPixelFilter, CA_AutoCorrect, DenoiseBlack                      | RAW 预处理          |
| [Output]                        | Format, Quality                                                   | 输出格式            |

### 曲线编码（实测校验，RT 5.13）

| 段.键 | 值格式 | 要点 |
| ----- | ------ | ---- |
| HSV Equalizer.HCurve / SCurve / VCurve | `类型;x1;y1;lt1;rt1;x2;y2;lt2;rt2;…` | 类型 1 = FCT_MinMaxCPoints（0 = 线性，等同关闭）；x/y/切点均为 0~1 浮点；恒等线 y=0.5；控制点 y 全为 0.5 时曲线被判 FCT_Empty（等于未开启）；切点统一 0.35 |
| ColorToning.Redlow…Bluehigh | 整数滑块 -100..100 | Splitco 用 `mixerToCurve`：值 ÷100 得 RGB 三元组 → 归一化求色相 → 染色强度 sat=(max−min)/2；某分区三通道全 0 则分区不染色 |

- 曲线 `Enabled` 键：RT 默认即为 1，映射层仅在至少一条曲线非恒等时才写入该段，避免产生无意义的 PP3 差异。
- ColorToning 的 `Balance` 仅 `Splitlr` 方法使用；LR 的 per-zone luminance（阴影/中间调/高光三档明度）在 `Splitco` 下无对应字段，映射层**不写入并在 stderr 明示已忽略**，不静默丢弃。

### 已知引擎保真差异（RT 5.13 实测，非映射层 bug）

| 项 | 差异 | 实测 |
| -- | ---- | ---- |
| 明度曲线阻尼 | `vCurve` 额外乘 `(1-(1-s)^4)`，灰像素（s=0）完全不受明度曲线影响 | 纯灰梯度图上明度用例 diff = 0.00 |
| 明度曲线无量程加倍 | `vCurve` 无 `*2` 系数（`sCurve`/`hCurve` 有），故 y=0.0 在线性工作空间把 V 减半，输出端仅 −27%（0.5^(1/2.2)） | lum −100 → ΔV ≈ −27%，lum +100 → ΔV ≈ +4.6 % |
| 工作空间放大 | 色相/饱和/明度曲线在线性化工作空间取值，输出 sRGB 后旋转量被放大 | 标称 +30° 的色相控制点实测峰值 Δhue ≈ +48~+70° |
| 稀疏插值带宽 | 8 锚点色相曲线经 FlatCurve 插值后有效带宽约 ±60° | 改为每 5° 钉点后收敛至 220–250°（±15° 级） |
| 染色强度受 Strength 约束 | `strProtect = pow(Strength/100, 0.4)`，默认 50 ⇒ 0.758 | 不写 Strength 与写 50 逐像素一致；写 100 后各用例 diff ×1.22~1.32 |
| 分区权重不等 | `rlo=strProtect`（阴影）、`rlm=1.5×`（中间调）、`rlh=2.2×`（高光） | 同滑块的染色强度随明度区递增 |
| 染色为逐通道加性 | `toningsmh()` 的 `corr = 20000×val×kl×strProtect`，非 HSV 混合 | 分区平均 ΔRGB 方向与目标色相一致，幅度随亮度连续变化 |

### grading_params.json 输入结构（易错点）

映射层接受的输入是**扁平**的 LR 风格字段。以下两种写法此前会静默失效（PP3 照常生成、画面无任何变化），
自 1.0.5 起 `grade.py` 会在 stderr 明确告警并忽略：

| 字段 | ✅ 正确 | ❌ 告警并忽略 |
| ---- | ------ | ------------- |
| `hsl` | `"hsl": [{"channel": "blue", "saturation": -40}, {"channel": "green", "hue": 20}]` —— **列表**，`channel` 取 red/orange/yellow/green/aqua/blue/purple/magenta，每项可带 `hue` / `saturation` / `luminance` | `"hsl": {"blue": {"saturation": -40}}`（对象或嵌套写法） |
| `color_grading` | `"color_grading": {"shadow_hue": 220, "shadow_saturation": 30, "highlight_hue": 40, "highlight_saturation": 25}` —— **扁平**键（`shadow_*` / `midtone_*` / `highlight_*`） | `"color_grading": {"shadow": {"hue": 220, "saturation": 30}}`（按区分组的嵌套写法） |

- 单通道数值绝对值 < 0.5 视为未调整，不写入曲线。
- 完整可用字段以 `photo-grader/scripts/grade.py` 中的 `rt_map_*()` 函数为准。

### 参数换算示例

| LR 输入              | RT 实际值                        | 说明              |
| -------------------- | -------------------------------- | ----------------- |
| exposure: +0.5       | Exposure.Compensation: +1.0      | x2.0 放大         |
| contrast: +50        | Exposure.Contrast: +40           | x0.8 缩放         |
| highlights: -50      | HLRecovery.Hlbl: 50              | 负值 → 高光恢复   |
| shadows: +30         | Exposure.ShadowCompr: 30         | 正值 →ShadowCompr |
| sharpen: amount 80   | Sharpening.DeconvAmount: 120     | x1.5              |
| noise_reduction: 40  | DPD.Luma: 56, Chroma: 35         | Lab 方法          |
| vignette_amount: -40 | Vignetting Correction.Amount: 60 | abs(x) × 1.5      |
| hsl blue hue +100    | HSV Equalizer.HCurve: `1;0;0.5;0.35;0.35;…;0.6667;0.5417;0.35;0.35;…;1;0.5;…` | 标称 +30°（实测因工作空间放大至 +52°） |
| color_grading 阴影 hue 220 / sat 40 | ColorToning.Redlow=0, Greenlow=13, Bluelow=40 | hsv(220°,1,1)×40 |
| color_grading 中间调 hue 40 / sat 60 | ColorToning.Redmed=60, Greenmed=40, Bluemed=0 | hsv(40°,1,1)×60 |
| color_grading 高光 hue 300 / sat 50 | ColorToning.Redhigh=50, Greenhigh=0, Bluehigh=50 | hsv(300°,1,1)×50 |
