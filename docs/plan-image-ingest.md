# 方案：离线文档支持图片（可选扩展）

> 状态：**已按 A 路线实施（2026-10-23）**。实施记录见 §8，原始评估内容保留在 §1–§7 以便追溯选型依据。

## 1. 现状核查（已读代码）

| 事实 | 位置 | 对方案的影响 |
|---|---|---|
| 只认 pdf/docx/pptx/md/markdown/txt | `rag/ingest/loaders.py:28` `SUPPORTED_SUFFIXES` | 加 3 个后缀即可打通上传校验、MIME、CLI 清单 |
| 上传白名单复用它 | `api/admin.py:128` `_safe_suffix()`，提示语"仅支持 PDF、DOCX、PPTX、Markdown、TXT" | 一处改，错误文案同步 |
| 上传**已落盘** | `api/admin.py:459` → `KNOWLEDGE_DIR/uploads/<shop>/<uuid><suffix>` | 原图有实体文件，`image_url` 可做受控回源，不需要新迁移 |
| 上传已有**魔数校验** `_magic_ok()` | `api/admin.py:78` | png/jpeg 补两条魔数分支即可挡"改后缀骗过白名单" |
| chunk 已有 `metadata_jsonb` | `db/models/knowledge.py:188` | 图片元数据直接存这里，**零迁移** |
| 引用链没有图片字段 | `rag/citations.py:20/41` → `agents/chat_service.py:1031 _citation` | 需加 `image_url/dimensions` 透传（4 处机械改动） |
| Pillow **已在依赖树里**（13.0.0，经 reportlab 传递引入） | `.venv` 实测 `import PIL` 成功 | 尺寸/格式校验不需要新依赖，只把它提升为直接依赖 |
| 现有非法格式测试 | `tests/unit/test_loaders.py:137` | 扩一个 `.gif` 断言即可覆盖"非法格式被拒" |

## 2. 三条候选路线

| | A. OCR（**推荐**） | B. 多模态描述 | C. 文本旁注（sidecar） |
|---|---|---|---|
| 做法 | RapidOCR 识别 → 文本块入库 | 视觉模型生成图片描述 → 描述入库 | 要求 `xxx.png` 旁必须有 `xxx.md`，只入 md |
| 新增依赖 | `rapidocr-onnxruntime` 1.4.4（实测解析出 6 个包：onnxruntime 1.31 / opencv-python 5.0 / shapely / pyclipper / flatbuffers），下载约 80 MB，镜像约 +250 MB；模型随 wheel 打包，**离线可用** | 无 Python 依赖，但要确认 DeepSeek-V4.1-Flash 是否支持图片输入（**未验证**），可能得另配视觉网关 | 无 |
| 确定性 | **高**：同图同文本，评测可重复 | 低：温度/模型一换，"检索命中"就漂 | 高 |
| 离线 | 是 | 否（每张图一次外网调用，关键缺失即入库失败） | 是 |
| 效果 | 合成截图 ≈99%，拍照/低清件下降 | 能描述版面与图形，但会漏精确数字（"7 天""24 个月"） | 取决于人手写 |
| 成本 | 0 元，1 次性建镜像 | 每图 ~1k token，重跑评测另算 | 0 |
| 工作量 | ≈1 人日 | ≈0.8 人日 + 模型可用性风险 | ≈0.2 人日 |
| 是否真满足"截图能被检索命中" | **是** | 是（但不可重复） | 否（等于绕开图片） |

**结论：选 A。** 理由三条：① 任务书原文是"离线文档"，OCR 不出网且可重复；② 政策截图的检索价值在**精确条款文字**，描述模型容易把"7 日"说成"一周"；③ 依赖虽非零，但比 paddlepaddle 方案（700 MB+、要 paddle 运行时）小一个量级，且不做只读演示。

为保留后路，OCR 抽成 `ImageTextExtractor` 协议，B 路线日后可作为第二个实现接入，不改 loader。

## 3. A 路线的实施清单

**产品代码（约 350 行）**

1. `rag/ingest/loaders.py`：`SUPPORTED_SUFFIXES` 加 `.png/.jpg/.jpeg`；新增 `_load_image()`：
   - Pillow 读尺寸并 `verify()` 校验真伪；沿用 Pillow 自带的 `MAX_IMAGE_PIXELS`（约 8948 万像素）
     防解压炸弹，另限 ≤ 10 MB（沿用 `knowledge_upload_max_bytes` 更严的一档）；
   - RapidOCR 出文本行 → 合并成 1 个 `ParsedBlock`（`page_no=1`，heading = 文档标题）；
   - 无文本 → `EmptyDocument`（与现在空文档同语义，不静默入库空块）。
2. `LoadedDocument` 增 `metadata: dict`，携带 `{"image": {filename, width, height, image_url, ocr_lines, ocr_confidence}}`；`pipeline.py` 写 chunk 时合并进 `metadata_jsonb`（**不需要迁移**）。
3. 引用回溯：`EvidenceChunk` / `Citation` 增 `image_url, image_width, image_height`；`retrieval.py` 从 chunk 行取、`_citation()` 与 `api/schemas.py` 透出。
4. 新增 `api/knowledge_assets.py`：`GET /api/v1/knowledge-images/{document_id}` —— 校验 `shop_id` + 文档可见性后按 `version.source_uri` 在 `KNOWLEDGE_DIR` 内解析（拒绝越界路径）并 `FileResponse` 返回原图。**不开公共静态目录**。
5. `api/admin.py` 错误文案 + `frontend/src/components/admin/DocumentUploadDialog.vue` 的 `ACCEPT` 加 `image/png,image/jpeg`。

**数据与测试**

6. `scripts/make_policy_screenshots.py`：用 Pillow 渲染 1 张 1080×1350 的政策截图（含"会员积分有效期 24 个月""过期不予补发"等可断言短语），字体按 `msyh.ttc → simhei.ttf → Noto Sans CJK` 顺序回退，**不写死 Windows 绝对路径**；产物入库 `data/knowledge/policy/member-points-screenshot-2026.10.1.png` + manifest 一条。
7. 单测：图片能出块且元数据含尺寸/文件名；`.gif` 被 `UnsupportedDocumentType` 拒绝；超大图被拒。
8. 集成：入库该图 → chunk `metadata_jsonb` 有 `image_url`；用金标问题检索，命中该文档且引用带 `image_url`。
9. **检索金标 58 → 61 条**：新增 3 条 `image-01/02/03`（同一张图 3 个不同问法，含 1 条"仅图上才有的信息"），`expected_titles` 指向该图片文档。

**文档**：`docs/06-api.md`（上传类型 + 引用新增字段 + 图片端点）、`docs/eval-report.md`（金标 58→61、新 sha、重跑的 R@k）、`docs/demo.md`、`README.md`、`docs/resume-evidence.md`。

## 4. 必须先讲清的代价与风险

1. **金标一变，评测口径全线连带**：`retrieval_cases.jsonl` 从 58 条变 61 条 → sha 变、R@1/MRR/ctxP 重算、`docs/eval-report.md:217` 与 `resume-evidence` 里的"58 条 / `856f3338…`"全部作废；`verify_stage13.py` 会按新数据复算，文档必须同步，否则复算不一致。**处理方式**：新增一份 `stage13-image-<ts>.json` 结果，旧的 `stage13-deepseek-20261023.json` 保留为历史，不改写。
2. **镜像变重**：api 镜像约 +250 MB（opencv + onnxruntime + 模型）。若不想让线上镜像背这个包袱，可拆成 `[ocr]` 可选依赖只装在 ingest 一侧——但那样 CI 里图片用例要么跳过（弱化验收），要么另建镜像，成本更高。**建议直接进主依赖**，理由是"入库能力"本就属于 api 进程。
3. **OCR 精度不是 100%**：合成截图稳，真实拍照件会掉字；政策数字识别错误比"没识别到"更危险。缓解：`ocr_confidence` 低于阈值时**拒答而不是入库低质块**，并在引用里标注"来源为图片识别"。
4. **评测要重跑**：需要本机 BGE-M3 + Milvus 重新索引（约 10–15 分钟），不是纯离线改动。
5. 前端只需一行 `ACCEPT`；引用面板展示缩略图属额外打磨，本次不做也能验收。

## 5. 工时拆解（A 路线）

| 环节 | 工时 |
|---|---|
| loader + 元数据 + 引用透传 + 图片端点 | 0.5 人日 |
| 单测/集成测试 + 非法格式 | 0.25 人日 |
| 截图生成脚本 + manifest + 3 条金标 + 重跑检索评测 | 0.15 人日 |
| 文档同步（6 个文件，含数字口径） | 0.1 人日 |
| **合计** | **≈1 人日** |

## 6. 验收对照

| 任务要求 | A 路线的落点 |
|---|---|
| 图片走 OCR 或多模态并说明理由 | 选 OCR，理由见 §2 |
| 保留 image_url / 文件名 / 尺寸，引用可回溯 | `metadata_jsonb.image` + `Citation.image_*` + `GET /knowledge-images/{id}` |
| 1 张含文字截图能被检索命中 | 集成测试 + 金标 `image-01..03` |
| 非法格式被拒 | `.gif/.bmp` → `UNSUPPORTED_FILE_TYPE`；扩展名伪装（png 内容为文本）→ Pillow `verify()` 拒绝 |
| pytest 全绿 + 金标加 3 条 | 791 → 约 800 passed；金标 58 → 61 |

## 7. 需要你决定

- **A（推荐）**：按本文做，含依赖 `rapidocr-onnxruntime`。
- **B**：多模态描述，需先确认可用视觉模型；确定性差，评测结论会不稳定。
- **C**：只做 sidecar 文本旁注，零依赖，但"截图可检索"这条不成立。
- **不做**：保持现状，在 `docs/eval-report.md` 的"限制"里写明图片暂不支持。

## 8. 实施记录（2026-10-23，A 路线）

**依赖实测**（不是估算）：`rapidocr-onnxruntime==1.4.4` + `onnxruntime==1.31.0`（43 MB）+
`opencv-python-headless`（113 MB）+ `shapely`（1.9 MB）+ `pyclipper` / `flatbuffers`，另把
`pillow` 提为直接依赖（它本来就在依赖树里）。为了让 slim 镜像不装 libGL，pyproject 加了
`[tool.uv] override-dependencies = ["opencv-python-headless"]`；Dockerfile 只额外装
`fonts-noto-cjk`（seed 渲染截图用）与 `libglib2.0-0`。

**落地改动**

| 文件 | 改动 |
|---|---|
| `rag/ingest/loaders.py` | `.png/.jpg/.jpeg` + `load_image()`（Pillow 校验尺寸/真伪 + RapidOCR 出块 + `LoadedDocument.metadata`） |
| `rag/ingest/pipeline.py` | `_document_metadata()` 把图片元数据与 `image_url` 合并进每个 chunk 的 `metadata_jsonb` 与 Milvus metadata |
| `rag/citations.py` / `rag/retrieval.py` | `EvidenceChunk.metadata`、`Citation.image_url/image_filename/image_width/image_height` |
| `agents/chat_service.py` / `api/schemas.py` | SSE `citation` 事件透出同四个字段（文本文档为 `null`） |
| `api/knowledge_assets.py` | `GET /api/v1/knowledge-images/{document_id}`：登录 + 同店 + 仅图片 + 路径必须在知识目录内 |
| `api/admin.py` | 白名单文案、PNG/JPEG 魔数校验、图片单独 10 MiB 上限 |
| `db/repositories/knowledge_scope.py` | `document_asset()` 读当前版本的 `source_uri` |
| `synthetic/image_render.py` / `writers.py` / `knowledge_corpus.py` | 语料新增 1 张 PNG 文档；`seed.py` 可从头重现（CJK 字体缺失直接报错） |
| `data/eval/retrieval_cases.jsonl` | 新增 `image-01..03`（143 条） |
| 前端 `DocumentUploadDialog.vue` | `accept` 与大小校验按类型区分 |

**验收数字**：`pytest` 804 passed / 2 skipped；`ruff check` 全绿；前端 typecheck 通过、vitest 149 passed；
图片类检索 **hit@3 3/3、hit@1 2/3、MRR 0.8333（hybrid）**，OCR 平均置信度 0.9965
（`data/eval/results/retrieval-image-20261023.json`，报告 §3.8）。

**与计划的偏差**：① 原计划单独写 `scripts/make_policy_screenshots.py`，实际改成把渲染挂进语料
writer，`scripts/seed.py` 一条命令即可重现，少一个需要人记的手工步骤；② 原计划「引用回溯」用静态
目录挂载，实际改成受鉴权端点（不暴露公共目录）；③ 依赖比估算稍重（opencv headless 113 MB），
靠 override 省掉了 libGL 一层。
