# P0 收尾验证 + P1 三主题修复实施计划

调研日期：2026-09-18。代码基线：`main@c754dc1`（4 个 P0 修复提交已在本地，**不 push**）。
本计划覆盖：① P0-2/P0-1 的浏览器端到端验收；② IMA #1500 脱敏取证能力与真实查询；③ P1 三个主题（#1412/#1392、#1228、#1501/#1491）。
原暂缓项：MinerU 真实 PDF/OCR 混合文件验收（用户此前指示"先放过"），代码修复（`55e20d2`）保留。2026-09-24 用户要求跳过 IMA 后继续其他计划，该验收重新检查了环境；本机缺少 MinerU CLI/模型与云端 token，故未执行真实解析，也未上传文件或安装大模型。

**当前收尾状态（2026-09-24）**：WP-A 已由 `ab89df6` 完成；WP-B 代码、测试和 CLI 已由 `26ee7c0` 完成；WP-F 层 2 安装器已由 `d41eb65`、`e188491`、`861f76c` 完成并通过隔离安装、离线 doctor 和桌面快捷方式分支验收；MinerU 历史捕获 fixture 映射已由 `388027b` 修正并验证。IMA 真实诊断问题已记录在 [`ima_real_diagnosis.md`](ima_real_diagnosis.md)，按用户指示暂停后续 IMA 查询和修复。官方 MinerU 4.0 迁移指南确认旧 `mineru -p` CLI 已变更；DeepTutor 当前适配器尚未迁移，因此本地版本检查和安装提示已收紧到 `>=3.4.5,<4`，修复提交为 `db6184a`。当前唯一待用户选择的工作是 MinerU 实时 PDF/OCR：安装隔离的 3.x CLI/模型、开发 4.x 适配、或配置云端并授权上传。桌面临时快捷方式清理被本机策略拦截，详见 §6.5。

---

## 一、调研结论

### 1. P0 收尾验证现状
- 后端 251 单测通过、前端 vitest 3 条通过、node 套件 1132 通过（4 个失败为无关基线架构扫描）。
- Playwright 已配置 `critical-turns` 与 `multi-worker-turns-desktop/mobile` 项目（[playwright.config.ts](file:///d:/AI_APP/deeptutor/web/playwright.config.ts#L20-L56)），现有 e2e 已覆盖跨 worker 恢复、取消、owner-loss 再生成（[multi-worker-turns.audit.ts](file:///d:/AI_APP/deeptutor/web/tests/e2e/multi-worker-turns.audit.ts#L96)），可复用其 harness 与 LLM/后端启动方式。
- 缺口：regenerate 被**拒绝**后的气泡恢复/Thinking 终止、quiz 卡片断线重连恢复、重复点击/并发不重复建回合，无端到端用例。

### 2. IMA #1500 取证
- Pipeline 已产出 `retrieval_status/source_count/evidence_chars`（[ima/pipeline.py:71-109](file:///d:/AI_APP/deeptutor/deeptutor/services/rag/pipelines/ima/pipeline.py#L71-L109)），远端调用经 `ImaClient.search_knowledge()`（[client.py:94-128](file:///d:/AI_APP/deeptutor/deeptutor/services/rag/pipelines/ima/client.py#L94-L128)），配置来自账号级 `settings/ima.json` + KB 级 `kb_config.json`（[config.py:61-127](file:///d:/AI_APP/deeptutor/deeptutor/services/rag/pipelines/ima/config.py#L61-L127)）。
- 已有 test-connect 端点（[knowledge.py:2315](file:///d:/AI_APP/deeptutor/deeptutor/api/routers/knowledge.py#L2315)），但不输出报告要求的逐层证据链（绑定来源→KB 指纹→远端业务码/条目数→识别文档数→hydrate 成败数→tool_result）。
- `_hydrate` 失败仅 warning 且刻意不记录含签名 URL 的内容（[pipeline.py:126-134](file:///d:/AI_APP/deeptutor/deeptutor/services/rag/pipelines/ima/pipeline.py#L126-L134)）——取证实现必须沿用该脱敏约束。

### 3. P1-1 学习状态不连续（#1412、#1392）
- 进入无 sessionId 的 mastery 路由时，前端 `newSession()` 只创建**本地 draft**（`makeDraftKey()` + dispatch，[ChatStateAdapter.tsx:2604-2609](file:///d:/AI_APP/deeptutor/web/features/chat/ChatStateAdapter.tsx#L2604-L2609)）；服务端会话在首条消息的 turn 中才隐式创建。
- 去重仅靠 `initializedRouteRef` 按 `routeKey` 拦截一次（[useMasteryStudySession.ts:133-145](file:///d:/AI_APP/deeptutor/web/hooks/useMasteryStudySession.ts#L133-L145)）；routeKey 抖动、StrictMode 双调用、快速切换 path 都可能产生多个 draft → 多个服务端会话（#1412 重复创建）。
- 绑定解析 `resolve_mastery_path_binding` 的最终回退是"用 session_id 造私有 path"（[identity.py:57-60](file:///d:/AI_APP/deeptutor/deeptutor/learning/identity.py#L57-L60)），configuration 在 draft 间污染时存在错绑风险。
- 面板数据来自 `/mastery-paths/topics/{id}/sessions` → `topic_sessions()` → `mastery_path_sessions` 表（[navigation.py:254-305](file:///d:/AI_APP/deeptutor/deeptutor/learning/navigation.py#L254-L305)、[storage.py:1184](file:///d:/AI_APP/deeptutor/deeptutor/learning/storage.py#L1184)）。未发过消息的 draft 不会落库 → 新建 path 后面板为空（#1392）。
- **最终修复形态需在复现后确认**，本计划先锁定复现与候选方案。

### 4. P1-2 403 空课程（#1228）
- 当前代码**已部分缓解**：`CoursesShelf` 已区分 loading / loadError / 空列表（[CoursesShelf.tsx:143-158](file:///d:/AI_APP/deeptutor/web/components/courses/CoursesShelf.tsx#L143-L158)），`expectJson` 非 ok 抛 `ApiError`（[courses-api.ts:131-149](file:///d:/AI_APP/deeptutor/web/lib/courses-api.ts#L131-L149)）。
- 残留缺口：错误态不区分 401/403（无权限）与网络/5xx；无诊断 ID；无"下一步"动作（登录/重试/切换账号）。`Promise.all([listCourses, listAllSessions])` 任一失败即整体报错，需确认 403 来自哪一调用。

### 5. P1-3 Windows 首启（#1501、#1491）
- `_spawn` 在 Windows 仅设 `CREATE_NEW_PROCESS_GROUP`，子进程继承父控制台（[launcher.py:278-282](file:///d:/AI_APP/deeptutor/deeptutor/runtime/launcher.py#L278-L282)）；`--detach` 路径才用 `DETACHED_PROCESS`（launcher.py:1038-1092）；[start_backend.bat](file:///d:/AI_APP/deeptutor/scripts/start_backend.bat) 直接开窗跑 python。
- 已有端口就绪轮询基础（launcher.py:531-553）。无 .vbs/pythonw 静默启动器，无一键安装脚本（scripts/ 仅有 bat 与 update.py）。

---

## 二、工作包与实施步骤（依赖排序）

### WP-E：P1-2 错误语义三态化（最小、最确定，先做）

**文件**
- `web/lib/courses-api.ts`：`ApiError` 携带 HTTP status；区分 listCourses 与 listAllSessions 的失败归因。
- `web/components/courses/CoursesShelf.tsx`：loadError 升级为 `{ kind: "forbidden" | "unavailable" | "unknown", message, requestId }`，三态渲染（空 / 无权限 / 加载失败），forbidden 态给"重新登录/检查账号"与重试按钮，失败态给重试 + 可复制诊断 ID。
- `web/shared/ui/EmptyState.tsx`：复用/扩展其变体（若已有 forbidden 变体则不新增）。
- 后端：确认错误响应是否带 request id（`system.py` diagnostics / 中间件）；缺则在错误 envelope 补 `request_id`（仅课程链路或全局，按现状最小化）。
- i18n：`web/locales/{en,zh}` 补文案（必须过 i18n:parity）。
- 测试：扩展 `web/tests/courses-shelf.spec.tsx`（403→forbidden 态；5xx/网络→unavailable 态；空数组→empty 态；诊断 ID 出现与可复制）。

### WP-C：P1-1 学习状态连续性（先复现，后修复）

**步骤**
1. 写失败测试复现：① React StrictMode/routeKey 快速变化下只产生一个 mastery draft；② 同一路由重复进入复用未提交 draft，不产生第二个服务端会话；③ draft 的 configuration 切换 path 后不残留旧 masteryPathId；④ 新建 path 后未发消息即返回面板的可见性预期（明确产品语义：显示"进行中/未开始"占位，而非空白）；⑤ 刷新后绑定关系一致。落点：`web/tests/mastery-*.test.ts(spec)` + 后端 `deeptutor/learning/tests/`。
2. 依据复现结果实施修复（候选，按测试选定）：
   - draft 幂等键：以 `(pathId, mode, courseId)` 复用未提交 draft，`newSession` 对同键调用去抖；
   - 首 turn 的"创建 session + bind path"在服务端同一原子边界完成，绑定随 TurnRequest.mastery_path_id 落库，杜绝 session_id 回退造 path（[identity.py:57](file:///d:/AI_APP/deeptutor/deeptutor/learning/identity.py#L57) 的 session-owned 回退仅用于真正无 path 场景，并加标记使面板可识别）；
   - #1392：path 创建即持久化一条"未开始"占位记录（或面板合并服务端 sessions 与当前 draft），刷新后仍可见；
   - 学习页/面板展示当前绑定的 path 名称，使绑定可见、可核对。
3. 后端测试：重复 start_turn 不重复建 session；错误 path 绑定被拒绝而非静默改写。

### WP-F：P1-3 Windows 首启（分两层，#1491 安装器单独评审）

**层 1（#1501 闪窗与误关，可本地验证）**
- `deeptutor/runtime/launcher.py`：新增 windowless detach 路径（Windows 组合 `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS | CREATE_NO_WINDOW`），前台 `start` 保持可见控制台、detach 完全无窗且与启动器控制台生命周期解耦。
- 新增 `scripts/start_deeptutor.vbs`（静默 `pythonw -m deeptutor_cli.main start --detach`）与可选桌面快捷方式说明；日志重定向到 `data/user/logs/launcher.log`，避免无窗时丢输出。
- 首启健康检查：复用端口轮询，失败时输出**可复制的修复步骤**（端口占用、模型未下载、前端未构建三类分别给建议）；新增 `deeptutor doctor`（若不存在）汇总后端/前端/端口/解析器就绪状态。
- 验证：本机以 vbs 启动 → 无闪窗 → 关闭任何残留控制台后服务仍存活；`doctor` 对各故障注入给出正确建议。

**层 2（#1491 一键安装，较大）**
- `scripts/install_windows.ps1`（或 .bat 引导 ps1）：检测 Python/Node → 建 venv → `pip install deeptutor`（或 -e）→ 前端依赖与构建/确认 packaged web → 放置 vbs 与快捷方式 → 运行 doctor。
- 该层在层 1 完成并验证后单独提交；是否纳入本轮由批准时决定。

### WP-B：IMA #1500 脱敏取证（先建能力，凭据到位再跑真实查询）

1. 扩展 test-connect（或新增 `GET /knowledge-bases/{kb}/diagnose-ima?query=`）：返回结构化证据——配置来源（account/kb 级覆盖标记）、knowledge_base_id 指纹（哈希前 8 位）、远端业务码/HTTP 状态、documents 与 folders 计数、识别为 source 的数量、hydrate 成功/失败数、evidence_chars、最终 retrieval_status。**严禁**返回 api_key、签名 COS URL、教材正文（沿用 [pipeline.py:128-134](file:///d:/AI_APP/deeptutor/deeptutor/services/rag/pipelines/ima/pipeline.py#L128-L134) 约束）。
2. 配套 CLI/脚本子命令便于受控查询（如 `deeptutor kb diagnose-ima <kb> --query "<教材唯一短句>"`），输出 JSON 证据报告。
3. 用户提供凭据后执行：同一教材唯一短句，覆盖 Web 与 Partner 两个入口的绑定解析，按报告三层假设（绑定错误 / 远端无命中或未索引 / 响应解析丢正文）逐层证伪，产出脱敏结论，再决定是否补修。
4. 将 `retrieval_status` 契约同步到 LlamaIndex 与 PageIndex（空结果/证据不足/错误三态），含测试。

### WP-A：P0 浏览器端到端回归（依赖本机可起服务，放最后但与各包可穿插）

新增 `web/tests/e2e/p0-regressions.audit.ts`，并在 playwright.config 注册项目：
1. regenerate 被服务端拒绝（构造校验失败/忙碌）→ 旧答案气泡恢复、Thinking 结束、出现可行动错误、不产生第二个 turn；
2. mastery 题卡：模拟断线重连后卡片以稳定 ID 恢复、不重复创建；
3. 附件 regenerate 成功路径：附件随回合保留、答案被替换；
4. 重复快速点击 regenerate：只建一个回合。
harness 复用 turn-lifecycle.audit.ts 的后端/LLM 处理方式（执行时先读该文件确认 mock 注入点）。

---

## 三、依赖与注意事项

- 全程本地提交、**不 push**；每个 WP 独立 conventional commit（参照已落地的 4 个提交格式）。
- 不提交 `.gitignore` 既有改动与 `web/public/pdfjs/wasm/*` 的 CRLF 噪音；不新增无关文档。
- 前端改动必须同步 `en/zh` locales，并通过 typecheck / 相关 node 测试；新增 `.test.ts` 走 `npm run test:node`，`.spec.ts(x)` 走 vitest。
- WP-C 的最终修复形态以第 1 步复现结果为准；若复现显示根因与候选方案不符，停下来说明并更新本计划，不硬做。
- WP-F 层 1 的"关窗后存活"只能在真实 Windows 会话验证（沙箱内无法完全证明 GUI/控制台生命周期）。
- IMA 取证与 e2e 真实执行依赖外部环境（凭据、本机服务）；代码与测试可先完成，执行结果单独汇报。

## 四、验证

- 后端：相关 `deeptutor/learning/tests`、rag/parsing 测试 + 新增诊断端点测试，pytest 全绿（exec_tool 的 3 个 Windows 基线失败除外）。
- 前端：vitest（新 spec）+ `test:node`（新 test）+ `typecheck` + `i18n:check`；基线既有的 4 个架构扫描失败不新增。
- WP-F：vbs 无窗启动、doctor 故障建议在本机实测。
- WP-A：Playwright 新项目在本机跑通；报告 P0 验收矩阵逐条勾选。
- WP-B：诊断报告经人工脱敏复核后才能外发/贴 issue。

## 五、风险

- **WP-C 根因不确定**：以失败测试先行锁定，避免按假设改错；最坏情况拆为"幂等去重"与"绑定/占位"两次提交。
- **WP-B 凭据与隐私**：凭据由用户提供且不落盘到仓库/日志；诊断输出默认脱敏，全文绝不入报告。
- **WP-F 层 2 安装器面广**：Python/Node 环境差异大，先交付层 1；层 2 若超期可独立为后续任务。
- **e2e 稳定性**：依赖真实服务时序，优先复用现有 harness 与串行模式（`PW_SERIAL=1`），避免引入 flaky 用例。
- **范围蔓延**：#1228 暴露出的"错误压扁"可能存在于其他页面；本轮只修课程页并沉淀三态模式，其他页面仅列清单不逐页改。

---

## 六、交接状态（Handoff，2026-09-24）

> 供新会话首读。基础工作包已推进到 `ab89df6`；WP-F 层 2 安装器于 `d41eb65` 提交，`e188491` 移除非必需 pip 自升级，`861f76c` 修正离线 doctor 兼容性。当前提交均在本地，未 push。

### 6.1 基线与已提交
已完成并**本地提交、均未 push**：
- `aed8e4e` — WP-E：课程库拒绝不再显示为空
- `f37324c` — WP-C：mastery 复用同主题草稿
- `6fe5f49` — WP-F 层 1：隐藏分离子控制台 + 启动诊断
- `26ee7c0` — **WP-B 完整提交**：IMA 脱敏取证 + 三态契约 + 路由/CLI/诊断测试
- `ab89df6` — **WP-A 完整提交**：4 个 Playwright e2e 回归 + regenerate 双重 bug 修复（in-flight 守卫 + rollback 顺序）
- `d41eb65` — **WP-F 层 2 提交**：Windows 安装脚本（发布 wheel、venv、VBS 启动器、可选桌面快捷方式、离线 doctor）
- `e188491` — **WP-F 层 2 修订**：跳过非必需的 pip 自升级，直接安装/升级 DeepTutor wheel
- `861f76c` — **WP-F 层 2 修订**：使用兼容的离线 `doctor` 命令，避免公开 wheel 拒绝 `doctor startup`

### 6.2 WP-B（已完成，提交于 `26ee7c0`）

所有代码、测试、CLI 入口均已提交。三态契约（error / no_hits / insufficient_content / ok）已在 LlamaIndex + PageIndex 两条管道补齐；LlamaIndex `needs_reindex` 早退也返回统一状态字段。`diagnose-ima` 路由与 CLI 均有输入错误、缺失 KB 和成功报告覆盖。

已验证：WP-B 相关五个测试文件共 241 项通过；`26ee7c0` 涉及文件的 Ruff 检查通过。该结果是针对性验证，不代表全仓 pytest 已运行。

**真实 IMA 凭据脱敏取证已执行**：诊断记录及本轮暂缓决定见 §6.5 和 [`ima_real_diagnosis.md`](ima_real_diagnosis.md)。

### 6.3 不得提交
- `.gitignore`（既有改动）
- `web/public/pdfjs/wasm/*`（CRLF 噪音）
- `.trae/`（计划文档目录，按需决定是否入库）

### 6.4 环境与命令
- 后端测试解释器：`C:\Users\49771\.codex\visualizations\2026\09\17\01a0aff7-521b-7270-af55-6b81ad6c0cf3\p0-test-env\Scripts\python.exe`（`C:\Python314\python.exe` 无 pytest）。
- 规范命令：
```powershell
& "...\p0-test-env\Scripts\python.exe" -m pytest <paths> -p no:cacheprovider -q 2>&1 | Select-Object -Last 25; Write-Output "PYTEST_EXIT=$LASTEXITCODE"
& "...\p0-test-env\Scripts\python.exe" -m ruff check <files>
```
- 该 venv 会打印沙箱 `.pyc` 写入的装饰性报错并在 shell 层 exit 1——**以 `PYTEST_EXIT=` 为准**。
- 前端：`node ./scripts/typecheck.mjs`；i18n `node ./scripts/i18n_parity.mjs`（不要用 `npm run typecheck`，沙箱内会失败）。
- 提交信息用 ASCII/英文（cp936 下提交钩子对非 ASCII 会崩溃）。

### 6.5 剩余事项
- **WP-A** 已完成（`ab89df6`）：新增 `web/tests/e2e/p0-regressions.audit.ts`（4 用例，`p0-regressions` 项目），`PW_SERIAL=1` 下本机跑通。修复两个真实 bug：同 tick 重复 regenerate + RESTORE_ASSISTANT rollback 顺序。
- **WP-B IMA 真实取证：本轮暂缓，问题已记录**：本机凭据文件被 Git 忽略；目标库 `初中数学资料大全` 已绑定为本地 IMA 指针。账号认证、目标库探测和主题词检索均成功；检索命中 10 条，但 4 个回拉目标的 `get_media_info` 均为 HTTP 200 / 业务码 220030，另对根目录 5 个媒体 ID 的回拉对照也全部返回该码；同查询的 11 条原始搜索结果均未带非空 `highlight_content`。解析阶段证据不足（`evidence_chars=0`），尚不能判为 DeepTutor 代码缺陷。用户已确认可在 IMA 客户端打开命中资料原文；故障现象集中在 OpenAPI `get_media_info` 回拉路径，但 `220030` 官方语义/适用范围未证实。**按用户指示暂停进一步 IMA 查询与修复**；不把问题标记为已解决。脱敏记录见 [`ima_real_diagnosis.md`](ima_real_diagnosis.md)。恢复条件：用户明确要求继续，且有 IMA 官方错误码/API 说明或获准使用另一自有库进行只读对照。
- IMA 查询回显 `query` 字段；分享版报告必须删改该字段，避免检索词泄露教材原文。本地报告不对外发送。
- **WP-F 层 2（Windows 一键安装器 #1491）已实现并提交 `d41eb65` / `e188491` / `861f76c`**：`scripts/install_windows.ps1` 检查运行时、建立 venv、安装发布版 `deeptutor` wheel、复制无窗启动器、可选创建桌面快捷方式，并运行离线 doctor。PowerShell 解析、`-WhatIf` 与隔离实装均通过：PyPI `deeptutor 1.6.11` 安装成功、doctor 必需检查通过、进程退出码为 0。另复用隔离安装验证桌面快捷方式目标、参数、工作目录和说明正确；临时快捷方式位于 `C:\Users\49771\OneDrive\Desktop\DeepTutor.lnk`，本机策略拒绝了清理操作，仍指向 `%TEMP%\DeepTutor-Installer-Smoke-*`。隔离安装目录也仍保留完整 venv。
- **MinerU 实时 PDF/OCR 验收仍待用户选择**：当前 PATH 找不到 MinerU CLI，常见 Hugging Face、ModelScope、MinerU 模型缓存目录不存在；隔离工具列表无 `uv` / `pipx`。本地 `document_parsing.json` 显示模式为 local、`local_cli_path` 为空、未配置 cloud token、`allow_local_model_download=false`；仅安装 Python 3.14.3，C 盘可用 44.1 GB、D 盘 189.5 GB、系统内存 15.7 GB、GPU 为 Intel UHD。官方 4.0 迁移说明旧 `mineru -p input.pdf -o output` 被替换；DeepTutor 当前仍使用该入口。已将版本检查限制为 `3.4.5 <= version < 4.0.0`，并同步设置页、doctor、启动提示和下载提示；新增 4.0.7 拒绝回归测试。提交 `db6184a`；相关解析/设置/doctor 三个测试文件 145 passed、2 skipped，Ruff 通过。后续路线需要用户选定：隔离安装 MinerU 3.x（需要与旧版兼容的 Python/依赖和模型；官方 3.4.5 Windows 指南列 Python 3.10–3.12、CPU pipeline、磁盘 20 GB+），或迁移适配器以支持 MinerU 4.x，或配置云 token 并明确授权测试 PDF 上传。参见[官方 3.4.5 安装指南](https://github.com/opendatalab/MinerU/blob/mineru-3.4.5-released/docs/en/quick_start/index.md)、[4.0 迁移指南](https://opendatalab.github.io/MinerU/reference/migration_4/)。本轮未安装依赖/模型、未发起实时解析或上传。历史认证 API v4 捕获 fixture 的 provenance 修正在 `388027b` 提交；映射用例通过。另修正 ingress 安全测试在 Windows 权限受限时的可移植性：仅对 WinError 1314 使用精确路径的 `Path.is_symlink()` 替身覆盖拒绝分支；完整 ingress 文件 11 项通过，Ruff 通过。此环境受限分支由替身验证，真实 symlink 创建行为仍需具备权限的平台验证。`55e20d2` 保留。

### 6.6 新会话建议首读
1. 本文件（六、交接状态）
2. `deeptutor/services/rag/pipelines/ima/diagnose.py`
3. 6.5 剩余事项与 `.trae/documents/p0_closeout_plan.md` §五

### 6.7 交接状态更新（2026-09-24 第二次会话）

基线推进到 `28e338f`；全部提交仍在本地、未 push。

新增提交（本轮）：
- `d1e0ddc` — **WP-B 收尾**：`diagnose-ima` 增加 `redact_query` 选项（服务参数 /
  REST `?redact_query=true` / CLI `--redact-query`），报告新增 `query_redacted` 字段；
  分享版报告不再需要手工删改 `query`（6.5 该条已闭环）。
- `34a1648` — **Windows 兼容**：`parsing/cache.py` 将 POSIX 根相对 `img_path`
  （`/abs/…`）视为绝对路径保留，修复 Python≥3.13 Windows 下被拼接为 `C:\abs\…` 的测试失败。
- `28e338f` — **测试兼容**：`test_lightrag_pipeline.py` 符号链接用例改用
  `5920501` 确立的"权限不足时模拟 is_symlink"方案（模拟补丁在歧义阶段前 `monkeypatch.undo()`）。

早前（handoff 后、本轮前）已完成：`d41eb65`/`e188491`/`861f76c` = **WP-F 层 2 一键安装器
`scripts/install_windows.ps1` 已提交**；`388027b`/`5920501`/`db6184a` = MinerU/LightRAG 测试兼容修复。

本轮验证（工作区 `.venv-p0test`，`--system-site-packages` + venv 内 `pytest-asyncio`、
venv 本地 `litellm==1.101.0 --no-deps`，绕开全局 site-packages 只读导致的 tiktoken 写入失败）：
- 后端：rag+parsing+诊断路由/CLI+turn-runtime+courses 定向 344 通过 / 2 跳过；
  新增 3 个 redact 测试与 lightrag 符号链接测试全绿；Ruff 对全部改动文件通过。
  graphrag adapter 12 项因本机未装可选 `graphrag` extra 而**合法 skip**（旧环境可跑）。
- 后端扩面扫尾（含 capabilities/multi_user）：**1281 passed / 19 skipped / 0 failed**。
- 前端：`typecheck` 通过；`i18n_parity` OK；vitest 新 spec 5/5；
  `run-node-tests` 1143 通过、仅基线既有 4 个架构扫描失败（数量与内容未新增）。
- WP-A 复核：本机 `next dev` + `PW_SERIAL=1 npx playwright test --project=p0-regressions`
  **4/4 通过**（会话结束后 dev server 已关闭）。
- WP-F 复核：`deeptutor doctor` 实机运行全 PASS 退出 0；vbs/installer 文件在位。

**唯一剩余外部依赖**（非代码）：IMA 内容回拉判定——需用户在 IMA 客户端人工打开
`初中数学资料大全` 命中条目验证原文可读性，以区分远端权限/OpenAPI 行为 vs 代码缺陷
（详见 6.5 与 `ima_real_diagnosis.md`；对外分享前改用 `--redact-query` 或删改 `query` 字段）。
其余计划项（WP-A/B/C/E/F 层1+层2、e2e、三态契约、验证矩阵）均已落地。

### 6.8 闭环记录（2026-09-29）

- **① IMA 220030 判定：已闭环（用户侧）**。用户已在 IMA 客户端人工核验命中条目，确认
  回答质量满足要求。据此不再将 `get_media_info` 业务码 220030 视为 DeepTutor 代码缺陷，
  6.5/6.7 的"唯一剩余外部依赖"清除，WP-B 至此完整闭环。`ima_real_diagnosis.md` 保留为取证档案。
- 提交基线 `28e338f` 已于 2026-09-29 纯 fast-forward 推送至 fork（DataAI123/DeepTutor），
  本地与远端 main 一致；"不 push"约定由用户指示取代，HKUDS origin 仍只读。
- 仍开放：MinerU 实时 PDF/OCR 验收待用户选定路线（推荐：迁移 4.x 适配，等待用户确认后先调研再实施）。
- **Windows 真实 symlink 分支：已闭环（2026-09-29）**。本机确认无符号链接权限
  （WinError 1314、无开发者模式、未提权），改由 fork CI（ubuntu runner）真链接执行验证通过。
  首轮 CI 抓出 3 个缺陷并已修复推送：`29048aa`（fixture PDF 被 git 误判文本、CRLF 归一化导致
  Linux 端 golden sha256 失配 → `.gitattributes` 钉 `tests/fixtures/** -text` + renormalize）、
  `ea5e09e`（7 个 P0/P1 文件未过 `ruff format --check` 门）、`6eae30b`（weknora 管理路由测试
  依赖磁盘 auth.json 的隔离缺陷 → monkeypatch AUTH_ENABLED）。复跑
  Tests workflow run 36505304166 @ `6eae30b`：**全 13 作业成功**（四 worker 项按 fixture 缺省
  skipped），Python Tests 3.11/3.12/3.13/3.14 全绿。注意：tests/api 其余文件仍存在依赖鉴权
  磁盘态的用例，全套件鉴权隔离硬化未在本轮范围。
