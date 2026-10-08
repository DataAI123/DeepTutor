# P0/P1 收尾整体计划（剩余项收敛）

制定日期：2026-09-18。基线：`main@26ee7c0`（本地提交，**全程不 push**）。
上游基线计划：[p0_p1_followup_plan.md](file:///d:/AI_APP/deeptutor/.trae/documents/p0_p1_followup_plan.md)。

> **执行状态以本文末尾 §十“当前收口记录”（2026-09-24）为准。** 本文前面的“待做/未开始”内容是执行前计划快照，WP-A/WP-B 已完成；WP-F 层 2 脚本已实现、提交并在隔离临时目录完成安装与离线 doctor 验收。

---

## 一、摘要（Summary）

本轮**只收尾剩余未完成项**，不重开已完成的工作包。

| 工作包 | 目标 | 本轮状态 |
| --- | --- | --- |
| **WP-A** | 新增 P0 浏览器端到端回归用例（regenerate 拒绝恢复 / mastery 题卡重连 / 附件 regenerate / 重复点击去重） | **已完成**：`ab89df6` |
| **WP-B** | IMA 脱敏取证能力、三态检索契约与真实环境诊断 | **代码/测试已完成**：`26ee7c0`；真实取证已执行，后续调查按用户指示暂缓，问题有本地记录 |
| **WP-F 层 2** | Windows 安装器 | `d41eb65` 新增脚本，`e188491` 去掉 pip 自升级，`861f76c` 改为兼容的离线 doctor；临时目录完整安装和 doctor 通过 |
| **MinerU** | 真实 PDF/OCR 验收 | 历史认证输出的 fixture 映射已验证；本轮实时解析仍缺本地 CLI/模型或云端 token |
| 文档更正 | 校正上游计划状态、记录延期和未决事项 | 本地文档，不入库 |

**范围更新（2026-09-24）**：用户要求跳过 IMA 后继续其他计划；此前排除的 WP-F 层 2 与 MinerU 验收重新纳入本轮。MinerU 只执行本地安全检查；真实云端上传/计费或本地多 GB 模型安装未获单独授权时不执行。
- WP-E / WP-C / WP-F 层 1 的重开——只做一次只读复核，不重做。

**成功标准**：
1. `web/tests/e2e/p0-regressions.audit.ts` 存在并在 playwright.config 注册；本机 `PW_SERIAL=1` 跑通；产出 P0 验收矩阵并逐条勾选。
2. IMA 真实诊断已产出本地脱敏记录；未决的 OpenAPI 回拉问题按用户指示暂缓，不作为关闭项或对外报告。
3. 每个工作包一个本地 conventional commit（ASCII message），**不 push**。

---

## 二、当前状态分析（Current State Analysis）

### 2.1 已提交基线（`git log` 实证）

```
26ee7c0 feat(rag): add redacted IMA forensics and uniform retrieval status   ← WP-B，已提交
6fe5f49 fix(launcher): hide detached child consoles and add startup diagnostics  ← WP-F 层 1
f37324c fix(mastery): reuse a topic's draft instead of minting a new session      ← WP-C
aed8e4e fix(courses): stop presenting a refused course library as empty           ← WP-E
c754dc1 fix(rag): distinguish IMA no-hits, weak evidence, and retrieval errors
```

**结论：上游计划 §6.1"WP-B 尚未提交"与 §6.2"WP-B 待做 5 步"已过期。** 经复核：
- `26ee7c0` 含 16 个文件（`ima/diagnose.py`、`ima/{__init__,client,envelope,pipeline,transport}.py`、`api/routers/knowledge.py`、`deeptutor_cli/kb.py`、`llamaindex/{errors,pipeline}.py`、`pageindex/pipeline.py` 与配套测试）。
- LlamaIndex 三态测试已补齐（`tests/services/rag/test_llamaindex_embedding_failures.py` 覆盖 `error` / `no_hits` / `ok` / `insufficient_content`）。
- `needs_reindex` 早返回缺口已修（`needs_reindex is True` 且 `retrieval_status == "error"`、`source_count == 0`、`evidence_chars == 0`）。
- 路由与 CLI 测试已存在：`tests/api/test_knowledge_router.py`（400/404/200 三例）、`tests/cli/test_kb_cli.py`（报告输出 + 未知 KB 退出码 1）。

### 2.2 工作区（`git status --porcelain` 实证）

```
 M .gitignore
 M web/public/pdfjs/wasm/*        (CRLF 噪音，10 个文件)
?? .trae/                          (计划文档目录，未跟踪)
```

无任何源码改动待提交 ⇒ **WP-A 尚未落笔**。

### 2.3 WP-A 零进度确认

- `web/tests/e2e/*.ts` 共 10 个文件，**不含** `p0-regressions.audit.ts`。
- [playwright.config.ts](file:///d:/AI_APP/deeptutor/web/playwright.config.ts) 未做任何改动：`ui-audit` 的 `testIgnore` 仍只有 `epub-reader` / `turn-lifecycle` / `multi-worker-turns` 三项，也没有 `p0-regressions` 项目块。

### 2.4 已核实的实现事实（WP-A 用例设计依据）

**路由与入口**
- 会话页真实存在：`web/app/(workspace)/chat/[sessionId]/page.tsx` ⇒ 确定性入口 `page.goto('/chat/${SESSION_ID}')`。
- `loadSession` 经 `getSession(sessionId)` 取 `/api/sessions/{id}`（[ChatStateAdapter.tsx:2019](file:///d:/AI_APP/deeptutor/web/features/chat/ChatStateAdapter.tsx#L2019)）。

**Mock 能力（已被验证可行）**
- 前端固定连 `url: "/ws"`，底层是原生 `WebSocket` ⇒ 可被 `page.routeWebSocket('**/ws', …)` 拦截。
- 全仓唯一可照抄样板：[video-learning.audit.ts](file:///d:/AI_APP/deeptutor/web/tests/e2e/video-learning.audit.ts#L158-L188)（`routeWebSocket` + `page.route('**/api/**')` + `json()` helper）。
- REST 播种样板：[reading-citation-material.audit.ts](file:///d:/AI_APP/deeptutor/web/tests/e2e/reading-citation-material.audit.ts#L82-L87)。

**帧解析闸门**（`web/contracts/parse/turn-event.ts`）：`protocol_version === '2.0'`、`turn_id` 非空、`seq >= 0`、`timestamp` 有限。

**regenerate 拒绝链路（场景 1 权威 oracle）**
- 唯一通道：`protocol_error` + `error_code: 'regenerate_rejected'` → `UnifiedTurnClient.toStreamEvent` 合成为 `error`，`metadata.turn_terminal = (error_code === 'regenerate_rejected' && Boolean(event.session_id))` ⇒ **mock 帧必须带真值 `session_id`**。
- 会话守卫（[ChatStateAdapter.tsx:1613-1614](file:///d:/AI_APP/deeptutor/web/features/chat/ChatStateAdapter.tsx#L1613-L1614)）：`metadata.reason === 'regenerate_rejected'` 且 `session_id` 与本地不一致 → 静默 return（可用于负半场）。
- 终结错误回滚（[ChatStateAdapter.tsx:1768-1807](file:///d:/AI_APP/deeptutor/web/features/chat/ChatStateAdapter.tsx#L1768-L1807)）：`turn_terminal` 为真且 reason ∈ {`regenerate_busy`,`nothing_to_regenerate`,`regenerate_rejected`} → 用 `pendingRegenerateRef` 执行 `RESTORE_ASSISTANT`。
- `RESTORE_ASSISTANT` 只弹"`content===''` 且 `events.length===0`"的尾行 ⇒ **拒绝后不要断言 assistant 行精确条数**。
- `regenerateLastMessage`（[ChatStateAdapter.tsx:2545-2574](file:///d:/AI_APP/deeptutor/web/features/chat/ChatStateAdapter.tsx#L2545-L2574)）：守卫 `!key` / `!session` / `!session.sessionId` / `session.isStreaming` / `!lastUser`；`stateRef` 由 `useLayoutEffect` 同步（[L1514-1516](file:///d:/AI_APP/deeptutor/web/features/chat/ChatStateAdapter.tsx#L1514-L1516)）。发 `{type:'regenerate', session_id, overrides:{language}}`——**无 command_id，无客户端防抖**。

**断线重连链路（场景 2）**
- `subscribe_turn` 触发条件（[ChatStateAdapter.tsx:2109-2120](file:///d:/AI_APP/deeptutor/web/features/chat/ChatStateAdapter.tsx#L2109-L2120)）：`loadedStatus === 'running'` 且 `activeTurn?.turn_id || activeTurn?.id` ⇒ 发 `{type:'subscribe_turn', turn_id, after_seq:0}`。
- `resolveLoadedRunStatus(status, updated_at*1000, Date.now(), timeout)`：持久化 `running` 只在**新鲜**时可信 ⇒ 播种必须给**新鲜 `updated_at`**。
- 题卡外壳（[mastery-question.ts:120-129](file:///d:/AI_APP/deeptutor/web/lib/mastery-question.ts#L120-L129)）：`event.type === 'tool_result'`，`event.metadata.tool_metadata.mastery_question = { question_id, prompt, question_type, objective:{name}, difficulty, attempt, options:[{label,body}], allow_free_text }`；`question_id` 必填。
- 卡组件（[MasteryQuestionCard.tsx](file:///d:/AI_APP/deeptutor/web/components/chat/home/MasteryQuestionCard.tsx#L192-L330)）：**无 `data-testid`**；根节点 `div.my-4.border-l-2.pl-4`；prompt 经 `InlineMarkdown` 渲染；有选项时渲染选项行，页脚含 `Skip this one`（可选）与 `Submit` 按钮（`disabled={locked || !answer}`）。
- 提交链路（[ChatWorkspace.tsx:2043-2063](file:///d:/AI_APP/deeptutor/web/features/chat/components/ChatWorkspace.tsx#L2043-L2063)）：`answerMasteryQuestion` → `sendMessage(..., { masteryAnswer: { question_id, text } })`，守卫 `!text || state.isStreaming` ⇒ 提交会**产生一条含 `question_id` 的 WS 命令**，可作为"稳定 ID"的断言点。

**断言面（场景 1 的 UI 判定，[ChatMessageList.tsx](file:///d:/AI_APP/deeptutor/web/features/chat/messages/ChatMessageList.tsx)）**
- `showActions = msgDone && hasVisibleMarkdownContent(msg.content)`
- `showRegenerate = !isStreaming && isLastAssistant && Boolean(pairedUserMessage) && (!pairedUserMessage?.capability || capability === 'chat') && (showActions || terminalErrorRetryable)`
- 错误卡片：`AlertCircle` + `terminalError.content || t('The turn was interrupted.')` + 仅 `showRegenerate` 时渲染 `t('Retry')` 按钮。
- 文案（en）：`Retry`、`Regenerate`、`The turn was interrupted.`（`web/locales/en/app.json`）。
- `web/features/chat` **无任何 `data-testid`**，也无字面 "Thinking" 文案 ⇒ "Thinking 结束"必须**结构化推断**（如 `Regenerate` 控件重新可用 / 错误卡片出现）。

**已证伪的做法**：复用 `turn-lifecycle.audit.ts` 的 harness —— 该文件依赖真实 4-worker + Redis fixture（`DEEPTUTOR_TURN_E2E_FIXTURE === '1'`）。**WP-A 必须 WS + REST 全面自 mock**。

---

## 三、假设与决策（Assumptions & Decisions）

| # | 决策 | 依据 |
| --- | --- | --- |
| D1 | 只做剩余项；已完成工作包仅只读复核 | 用户选择"只收尾剩余未完成项" |
| D2 | WP-B 真实取证纳入本轮，凭据由用户提供 | 用户选择"纳入，我提供凭据并复核脱敏报告" |
| D3 | WP-A 以"本机起服务跑通 + 出验收矩阵"为完成标准 | 用户选择"本机起服务跑通并出验收矩阵" |
| D4 | 完整 WS+REST 自 mock，不依赖真实后端与 LLM | `turn-lifecycle` harness 依赖不可用的 fixture |
| D5 | 不修改任何生产组件（含不加 `data-testid`） | 保持本工作包"只加测试"的边界；断言改用可见文本与 WS 命令 |
| D6 | 沿用原提交与卫生约束：不 push、不提交 `.gitignore` / `web/public/pdfjs/wasm/*`、`.trae/` 不入库 | 用户选择"沿用原约束" |
| D7 | 上游计划文档的更正为**本地文档改动**，随 `.trae/` 一起不入库 | 同 D6 |
| D8 | 前端新增文件只用既有依赖 | `web/package.json` 已有 `@playwright/test` |

---

## 四、WP-A 实施细节（Proposed Changes）

### 4.1 新增 `web/tests/e2e/p0-regressions.audit.ts`

**风格**：与 `video-learning.audit.ts` 一致——单引号、无分号、`import { expect, test } from '@playwright/test'`。

**常量**

```ts
const SESSION_ID = 'p0-regression-session'
const TURN_ID = 'turn-1'
const ORIGINAL = 'Original answer'
const REVISED = 'Revised answer'
const PROMPT = 'What does entropy measure?'
const QUESTION_ID = 'q-stable-1'
```

**公共 harness（文件内共享函数）**

```ts
type Command = Record<string, unknown>

function mockApi(page, sessionPayload: () => Record<string, unknown>) { ... }
function mockSocket(page, commands: Command[], onCommand?: (c: Command, socket) => boolean) { ... }
```

- `mockApi`：`page.route('**/api/**', …)`，先匹配具体路径，最后 `return json({})` 兜底：
  - `/api/auth/status` → `{ enabled: false, authenticated: true, role: 'admin', is_admin: true }`
  - `/api/settings/ui` → `{ language: 'en' }`
  - `/api/capabilities/registered` → `{ capabilities: [{ id: 'chat', kind: 'turn', available: true }] }`
  - `/api/settings` → `{ catalog: {} }`
  - `/api/settings/llm-options` → `{ active: { profile_id: 'p', model_id: 'm' }, options: [] }`
  - `/api/dashboard/suggestions` → `{ suggestions: [], stale: false }`
  - `/api/sessions/${SESSION_ID}` → `sessionPayload()`
  - `/api/sessions` → `{ sessions: [] }`
- `mockSocket`：`page.routeWebSocket('**/ws', socket => { socket.onMessage(raw => { const cmd = JSON.parse(String(raw)); commands.push(cmd); onCommand?.(cmd, socket) }) })`。
- 帧构造 helper：

```ts
const frame = (type: string, seq: number, extra: Record<string, unknown> = {}) => ({
  protocol_version: '2.0', type, session_id: SESSION_ID, turn_id: TURN_ID,
  seq, source: 'chat', stage: 'responding', timestamp: Date.now() / 1000,
  content: '', metadata: {}, ...extra,
})
```

**会话播种基线**（除场景 2 外）

```ts
{
  id: SESSION_ID, session_id: SESSION_ID, title: 'P0 regression',
  created_at: 1, updated_at: Math.floor(Date.now() / 1000),
  status: 'idle', preferences: { capability: 'chat' }, active_turns: [],
  messages: [
    { id: 1, role: 'user', content: 'Explain entropy', events: [], attachments: [] },
    { id: 2, role: 'assistant', content: ORIGINAL, events: [], attachments: [] },
  ],
}
```

> `status:'idle'` + `active_turns:[]` ⇒ **不应**发出 `resume_turn` / `subscribe_turn`（可作为基线断言）。

---

#### 用例 1：`regenerate 被服务端拒绝 → 旧答案恢复、可行动错误、不产生第二个回合`

1. 播种基线会话；`page.goto('/chat/' + SESSION_ID)`。
2. `await expect(page.getByText(ORIGINAL)).toBeVisible()`。
3. `const regen = page.getByRole('button', { name: 'Regenerate' })`；`await expect(regen).toBeVisible()`。
4. `await regen.click()`；断言 `commands` 末条为 `{ type: 'regenerate', session_id: SESSION_ID }`。
5. 断言旧答案已弹出：`await expect(page.getByText(ORIGINAL)).toHaveCount(0)`（同时即"Thinking 已开始"）。
6. **负半场**：`socket.send(JSON.stringify({ protocol_version:'2.0', type:'protocol_error', error_code:'regenerate_rejected', message:'Please retry', retryable:true, session_id:'different-session', turn_id:TURN_ID, seq:9, timestamp: Date.now()/1000 }))` → 断言 `getByText(ORIGINAL)` 仍 `toHaveCount(0)`，且 `getByText('Please retry')` 不可见（守卫生效）。
7. **正半场**：同帧但 `session_id: SESSION_ID` → 断言 `getByText(ORIGINAL)` 恢复可见、`getByText('Please retry')` 可见、`Retry` 按钮可见、`Regenerate` 按钮重新可用。
8. **不产生第二个回合**：`commands.filter(c => c.type === 'regenerate').length === 1` 且 `commands.filter(c => c.type === 'start_turn' || c.type === 'submit_user_reply').length === 0`。
9. 断言从未发出 `resume_turn` / `subscribe_turn`。

> 注意：**不断言 assistant 行条数**（`RESTORE_ASSISTANT` 语义，见 §2.4）。

#### 用例 2：`mastery 题卡断线重连后以稳定 ID 恢复、不重复创建`

**播种**：`status: 'running'`，`active_turns: [{ turn_id: TURN_ID }]`，`updated_at: Math.floor(Date.now()/1000)`（新鲜），`messages` 只有 user 行。

**onCommand 处理**：
- `subscribe_turn` → 断言收到 `{ type:'subscribe_turn', turn_id: TURN_ID, after_seq: 0 }`；随后依次 `socket.send`：
  1. `frame('session', 1, { turn_id: TURN_ID })`
  2. `frame('tool_result', 2, { stage: 'responding', metadata: { tool: 'mastery_quiz', tool_metadata: { mastery_question: { question_id: QUESTION_ID, prompt: PROMPT, question_type: 'single_choice', objective: { name: 'Thermodynamics' }, difficulty: 'easy', attempt: 1, options: [{ label: 'A', body: 'Disorder' }, { label: 'B', body: 'Energy' }], allow_free_text: false } } } })`
  3. `frame('done', 3, { metadata: { status: 'completed' } })`

**断言（第一次）**
- `await expect(page.getByText(PROMPT)).toHaveCount(1)`。
- 点选项 `A`，点 `Submit`；断言 `commands` 中存在一条命令，其 `JSON.stringify(cmd)` 包含 `QUESTION_ID`（稳定 ID 随提交出站）。

**断线重连（同页重载）**
- 第二次 `page.goto('/chat/' + SESSION_ID)`；此时 REST 播种改为"已持久化的 assistant 消息"，其 `events` 含上面第 2 帧同构的 `tool_result`（`metadata.tool_metadata.mastery_question.question_id === QUESTION_ID`），`status: 'idle'`, `active_turns: []`。
- 断言：`getByText(PROMPT)` **`toHaveCount(1)`（不重复创建）**；`Submit` 可用；未发出新的 `subscribe_turn`。

#### 用例 3：`附件 regenerate 成功路径：附件随回合保留、答案被替换`

1. 播种：user 行带 `attachments: [{ id: 'att-1', name: 'lecture-notes.pdf', kind: 'document' }]`（字段名执行时以 `web/features/chat/controllers/pending-attachments.ts` 与消息模型为准，先读该文件确认），assistant 行 `content: ORIGINAL`。
2. `goto` → `await expect(page.getByText('lecture-notes.pdf')).toBeVisible()`。
3. 点 `Regenerate`；onCommand 收到 `regenerate` 后回三帧：
   `session`(seq 1) → `content`(seq 2, `content: REVISED`) → `done`(seq 3, `metadata: { status: 'completed', assistant_message_id: 2 }`)。
   > `done` 必须带 `assistant_message_id` 以走 `RECONCILE_TURN` 就地更新（否则触发全量 `loadSession`）。
4. 断言：`getByText(REVISED)` 可见、`getByText(ORIGINAL)` `toHaveCount(0)`、`getByText('lecture-notes.pdf')` 仍可见、`regenerate` 命令计数为 1。

#### 用例 4：`重复快速点击 regenerate：只建一个回合`

1. 播种基线会话；`goto`；等 `Regenerate` 可见。
2. onCommand **只记录、不回复**（保持该 turn 存活，`isStreaming` 维持为真）。
3. `const handle = await regen.elementHandle()`；`await regen.click()`。
4. 立即二次激活（既覆盖"控件消失"的 UI 保护，也覆盖最坏的同 tick 情况）：
   `await page.evaluate(() => { const b = document.querySelector('button'); })` 不适用 ⇒ 改用
   `await handle?.dispatchEvent('click').catch(() => {})`（元素若已卸载，异常被吞掉；若仍挂载，则同 tick 二次触发）。
5. `await expect(regen).toHaveCount(0)`（回合存活期间控件消失）。
6. `await page.waitForTimeout(300)`。
7. 断言不变式：`commands.filter(c => c.type === 'regenerate').length === 1`，且 `start_turn` / `submit_user_reply` 计数为 0。

> **若第 7 步实测出现 2 条 `regenerate`（即同 tick 二次激活绕过了守卫）**：这是一个真实的 P0 缺口，按 §六 处理（在 `regenerateLastMessage` 增加 in-flight 守卫，镜像 `pendingRegenerateRef`），不要放宽断言。
> **若 `dispatchEvent` 在已卸载句柄上抛错导致不稳定**：退化为 `regen.click()` + `toHaveCount(0)` + 计数不变式，并在测试内注释说明退化原因。

### 4.2 修改 `web/playwright.config.ts`

两处最小改动：

1. `ui-audit.testIgnore` 追加 `"**/e2e/p0-regressions.audit.ts"`（防止被 `**/*.audit.ts` 重复收走）。
2. `projects` 追加：

```ts
{
  name: "p0-regressions",
  testMatch: "**/e2e/p0-regressions.audit.ts",
  use: { ...devices["Desktop Chrome"], reducedMotion: "reduce" },
},
```

（`reducedMotion: "reduce"` 与既有 `multi-worker-turns-*` 保持一致，压制动画导致的可见性抖动。）

### 4.3 明确不做

- 不修改 `ChatMessageList.tsx` / `MasteryQuestionCard.tsx` / `ChatStateAdapter.tsx`（除非用例 4 暴露真实缺口，见 §六）。
- 不新增依赖、不改 locales（本工作包无用户可见文案变更）。

---

## 五、WP-B 收尾：真实凭据脱敏取证

前提：能力与测试已在 `26ee7c0` 交付，本节只做**真实执行**。

1. **凭据落位（不入库）**：按 [config.py:61-127](file:///d:/AI_APP/deeptutor/deeptutor/services/rag/pipelines/ima/config.py#L61-L127) 的账号级 `data/user/settings/ima.json` 或 KB 级 `kb_config.json` 写入用户提供的 IMA 凭据。
   - 执行前确认该路径处于 `.gitignore` 覆盖范围；若不在，**先加入忽略再写入**，并在完成后复核 `git status` 无凭据文件出现。
2. **受控查询**：选一句教材中**唯一**的短句作为探针，分别覆盖 Web 入口与 Partner 入口的绑定解析：

```powershell
& "<p0-test-env>\Scripts\python.exe" -m deeptutor_cli.main kb diagnose-ima <kb-name> --query "<教材唯一短句>"
```

   （等价入口：`GET /knowledge-bases/{kb}/diagnose-ima?query=`。）
3. **逐层证伪**（对应上游计划的三层假设）：
   - 层 1 绑定错误 → 看报告里的配置来源标记（account/kb 覆盖）、`knowledge_base_id` 指纹前 8 位是否与目标 KB 一致。
   - 层 2 远端无命中/未索引 → 看远端业务码 / HTTP 状态、`documents` 与 `folders` 计数、识别为 source 的数量。
   - 层 3 响应解析丢正文 → 看 hydrate 成功/失败数、`evidence_chars`、最终 `retrieval_status`。
4. **脱敏复核**：报告**严禁**包含 `api_key`、签名 COS URL、教材正文（沿用 [pipeline.py:126-134](file:///d:/AI_APP/deeptutor/deeptutor/services/rag/pipelines/ima/pipeline.py#L126-L134) 约束）。产出后由用户人工复核通过，方可外发/贴 issue。
5. **结果分流**：
   - 三层全部证伪且拿到正文 ⇒ #1500 关闭，结论写入报告。
   - 任一层坐实 ⇒ 新增**独立** commit 修复（不与 WP-A 混提）。
   - 凭据不可用/被拒 ⇒ 记录为阻塞，`diagnose-ima` 能力保持已交付状态，不降级。

---

## 六、缺口处置（仅在实测暴露时执行）

仅当 WP-A 用例 4 第 7 步失败（同 tick 二次激活产生 2 条 `regenerate`）时：

- 在 `regenerateLastMessage`（[ChatStateAdapter.tsx:2545](file:///d:/AI_APP/deeptutor/web/features/chat/ChatStateAdapter.tsx#L2545)）增加一个 in-flight 守卫：以 `regenerateInFlightRef: Set<string>`（key 维度）在发起时置位、在 `done` / `error(turn_terminal)` 路径清除，命中即 `return`。
- 复查 `web/tests/chat-regenerate-rejection.spec.tsx`（vitest）不回归。
- 该修复作为**独立** commit，与本工作包解耦。

---

## 七、验证（Verification）

### 7.1 命令

```powershell
# 1) 静态检查（沙箱内不要用 npm run typecheck）
node ./scripts/typecheck.mjs
npx eslint tests/e2e/p0-regressions.audit.ts

# 2) 起前端（config 无 webServer 块，必须手动起）
#    在 web/ 下后台运行：
npm run dev

# 3) 跑新项目（串行，避免 flaky）
$env:PW_SERIAL="1"; npx playwright test --project=p0-regressions

# 4) 确认新文件未被 ui-audit 重复收走
npx playwright test --project=ui-audit --list
```

### 7.2 P0 验收矩阵（执行后逐条勾选）

| # | 验收点 | 覆盖用例 | 结果 |
| --- | --- | --- | --- |
| 1 | regenerate 被拒 → 旧答案气泡恢复 | 用例 1 | ☐ |
| 2 | regenerate 被拒 → Thinking/流式状态终止（`Regenerate` 控件恢复可用） | 用例 1 | ☐ |
| 3 | regenerate 被拒 → 出现可行动错误（错误文案 + `Retry`） | 用例 1 | ☐ |
| 4 | regenerate 被拒 → 不产生第二个回合 | 用例 1 | ☐ |
| 5 | 守卫负半场：`session_id` 不匹配时静默忽略 | 用例 1 | ☐ |
| 6 | mastery 题卡断线重连后恢复 | 用例 2 | ☐ |
| 7 | mastery 题卡以稳定 ID 恢复（提交命令携带 `question_id`） | 用例 2 | ☐ |
| 8 | mastery 题卡不重复创建（重载后计数 == 1） | 用例 2 | ☐ |
| 9 | 附件 regenerate 成功 → 附件随回合保留 | 用例 3 | ☐ |
| 10 | 附件 regenerate 成功 → 答案被替换 | 用例 3 | ☐ |
| 11 | 重复快速点击 regenerate → 只建一个回合 | 用例 4 | ☐ |
| 12 | 静态检查：typecheck + eslint 通过 | — | ☐ |

### 7.3 文档更正（本地，不入库）

- 更新 [p0_p1_followup_plan.md](file:///d:/AI_APP/deeptutor/.trae/documents/p0_p1_followup_plan.md) §6.1 / §6.2 / §6.5：
  - §6.1：补记 `26ee7c0` 已提交（WP-B 代码 + 测试 + 三态契约）。
  - §6.2：整节标记为**已完成**，删除已过期的"待做 5 步"。
  - §6.5：WP-A 由"完全未开始"改为"已完成"，并记录新文件与项目名。

---

## 八、风险与缓解

| 风险 | 缓解 |
| --- | --- |
| e2e 时序抖动（Playwright 动作与 React 提交竞态） | 全 mock、`PW_SERIAL=1`、`reducedMotion: 'reduce'`；断言不变式（命令计数）而非触发次数 |
| 用例 4 的二次激活在不同 React 调度下行为不一致 | 采用"最坏同 tick 激活 + 容错吞异常"，并给出退化路径；失败即视为真实缺口按 §六 处理 |
| 题卡无 `data-testid` | 用唯一 prompt 文本 + 计数断言；稳定 ID 用出站命令内含 `question_id` 断言（D5：不改生产组件） |
| `attachments` 字段名与消息模型不一致 | 用例 3 执行前先读 `pending-attachments.ts` 与消息模型确认字段后再定稿 |
| 无 `webServer` 配置导致"跑不通"被误判为实现问题 | §7.1 明确要求先手动 `npm run dev`；若本机 3000 端口被占用，用 `WEB_BASE_URL` 覆盖 |
| IMA 凭据泄漏 | 凭据仅落 `data/user/settings/*.json`（先确认被忽略）、不落日志、报告脱敏后人工复核 |
| 真实凭据不可得 | WP-B 真实执行为可阻塞项；`diagnose-ima` 能力保持已交付，不阻塞 WP-A 收尾 |

---

## 九、执行顺序与提交计划

1. **只读复核**（已完成，见 §二）：`git log` / `git status` / e2e 目录 / playwright.config。
2. **WP-A**：新建 `web/tests/e2e/p0-regressions.audit.ts` → 改 `web/playwright.config.ts` → 起服务跑通 → 填 §7.2 矩阵。
3. **提交 A**（仅当矩阵全绿；若用例 4 失败则先做 §六 修复并拆为提交 B）：

```
test(chat): add P0 browser regressions for regenerate and mastery reconnect
```

   提交内容仅含：`web/tests/e2e/p0-regressions.audit.ts`、`web/playwright.config.ts`。
   **不得** `git add` `.gitignore`、`web/public/pdfjs/wasm/*`、`.trae/`。
4. **WP-B 真实取证**：凭据落位 → `kb diagnose-ima` → 脱敏复核 → 结论；如需修复代码则单独 commit。
5. **文档更正**（§7.3，本地 `.trae/`，不入库）。
6. 全程**不 push**；结束后向用户汇报验收矩阵与 IMA 结论。

---

## 十、当前收口记录（2026-09-24）

- **WP-A 已完成并提交**：`ab89df6`。4 个浏览器回归用例和 `p0-regressions` Playwright 项目已加入；此前记录的 `PW_SERIAL=1` 验收为 4/4 通过。实现过程中修复了重复 regenerate 与拒绝回滚顺序问题。详细状态见上游计划 §6.5。
- **WP-B 代码与测试已完成并提交**：`26ee7c0`。相关 241 项测试和 Ruff 检查通过；真实 IMA 诊断也已执行并保存在 [`ima_real_diagnosis.md`](ima_real_diagnosis.md)。
- **IMA 未决问题按用户指示暂缓**：搜索可命中内容、IMA 客户端可打开原文，但 OpenAPI `get_media_info` 的回拉返回 HTTP 200 / 业务码 `220030`，导致 `evidence_chars=0`。该业务码的官方含义尚未核实；当前证据不足以归因 DeepTutor 代码问题。暂停进一步查询和修复，不宣称问题已关闭；恢复时先核实官方接口/错误码说明或另行取得只读对照授权。报告仅本地留存，不外发。
- **WP-F 层 2 已完成并提交**：`d41eb65` 新增 `scripts/install_windows.ps1`，`e188491` 移除非必需 pip 自升级，`861f76c` 改用兼容的离线 `doctor` 命令。脚本检查 64 位 Python 3.11–3.14 与 Node.js ≥20.9，建立 venv、安装发布版 wheel、复制 VBS 启动器、可选创建桌面快捷方式并运行离线诊断。PowerShell 语法、`-WhatIf` 与隔离实装均通过：PyPI `deeptutor 1.6.11` 安装成功，doctor 必需检查通过，进程退出码 0；本次复用隔离安装实测快捷方式目标、参数、工作目录和说明均正确。测试快捷方式位于 `C:\Users\49771\OneDrive\Desktop\DeepTutor.lnk`，指向 `%TEMP%\DeepTutor-Installer-Smoke-*`；清理命令被本机策略拒绝，暂时留在桌面。隔离安装目录也仍保留完整 venv。
- **MinerU 实时验收未完成**：当前 PATH 未发现 `mineru` CLI，常见 Hugging Face、ModelScope、MinerU 模型缓存目录不存在，设置为本地模式且没有云 token；未上传 PDF、未安装模型、未调用计费 API。修复 `55e20d2` 保留。历史认证 API v4 捕获 fixture 的 provenance 已修正并提交 `388027b`；Sidecar 映射用例通过，完整 ingress 文件现为 11 项通过。为适配 Windows WinError 1314，symlink 拒绝测试在无法创建链接时对精确路径替身 `Path.is_symlink()`，未跳过断言；该受限分支已验证，真实文件系统 symlink 创建仍需有权限的平台验证。官方 4.0 迁移已确认旧 `mineru -p` 入口被替换；提交 `db6184a` 限制本地 CLI 接受版本在 `3.4.5 <= version < 4.0.0`，安装/doctor 提示已同步，相关 145 tests passed、2 skipped。当前只有 Python 3.14.3，机器 15.7 GB RAM / Intel UHD / D 盘 189.5 GB 可用；后续需用户选择隔离安装兼容 3.x CLI/模型、开发 4.x 适配，或授权云端上传测试文件。
- **本轮范围与仓库卫生**：代码/fixture/测试提交 `d41eb65`、`e188491`、`861f76c`、`388027b`、`5920501` 均在本地、未 push；计划与 IMA 报告仍只留在 `.trae/documents/`。`.gitignore`、`web/public/pdfjs/wasm/*` 及其他既有工作区改动保持原状。
