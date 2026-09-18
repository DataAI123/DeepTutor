import { expect, test, type Page, type WebSocketRoute } from '@playwright/test'

const SESSION_ID = 'p0-regression-session'
const TURN_ID = 'p0-turn'
const ORIGINAL = 'Original answer about entropy.'
const REVISED = 'Revised answer grounded in the lecture notes.'
const QUESTION_ID = 'q-stable-1'
const QUESTION = 'What does entropy measure?'
type Command = Record<string, unknown>

function frame(type: string, seq: number, extra: Command = {}) {
  return {
    protocol_version: '2.0', type, session_id: SESSION_ID, turn_id: TURN_ID,
    seq, source: 'chat', stage: 'responding', timestamp: Date.now() / 1000,
    content: '', metadata: {}, ...extra,
  }
}

function session() {
  return {
    id: SESSION_ID, session_id: SESSION_ID, title: 'P0 regression',
    created_at: 1, updated_at: Date.now() / 1000,
    status: 'idle', preferences: { capability: 'chat' }, active_turns: [],
    messages: [
      { id: 1, parent_message_id: null, role: 'user', content: 'Explain entropy', events: [], attachments: [] },
      { id: 2, parent_message_id: 1, role: 'assistant', content: ORIGINAL, events: [], attachments: [] },
    ],
  }
}

async function mockRuntime(page: Page, payload: () => Command = session) {
  const commands: Command[] = []
  const sockets: WebSocketRoute[] = []
  await page.routeWebSocket('**/ws', socket => {
    sockets.push(socket)
    socket.onMessage(raw => commands.push(JSON.parse(String(raw)) as Command))
  })
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    const json = (value: unknown) => route.fulfill({ json: value })
    if (path === `/api/sessions/${SESSION_ID}`) return json(payload())
    if (path === '/api/auth/status')
      return json({ enabled: false, authenticated: true, role: 'admin', is_admin: true })
    if (path === '/api/settings/ui') return json({ language: 'en' })
    if (path === '/api/capabilities/registered')
      return json({ capabilities: [{ id: 'chat', kind: 'turn', available: true }] })
    if (path === '/api/settings') return json({ catalog: {} })
    if (path === '/api/settings/llm-options')
      return json({ active: { profile_id: 'p', model_id: 'm' }, options: [] })
    if (path === '/api/dashboard/suggestions') return json({ suggestions: [], stale: false })
    if (path === '/api/sessions') return json({ sessions: [] })
    return json({})
  })
  return {
    commands, sockets,
    ofType: (type: string) => commands.filter(command => command.type === type),
    send: (event: Command) => sockets.at(-1)!.send(JSON.stringify(event)),
  }
}

async function openSession(page: Page) {
  await page.goto(`/chat/${SESSION_ID}`)
  await expect(page.getByText(ORIGINAL, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Regenerate', exact: true })).toBeEnabled()
}

function done() {
  // Reconcile in place; a real persisted message id avoids a REST reload.
  return frame('done', 3, { metadata: { status: 'completed', assistant_message_id: 2 } })
}

test('rejected regenerate restores the answer and offers retry without starting another turn', async ({ page }) => {
  const runtime = await mockRuntime(page)
  await openSession(page)
  await page.getByRole('button', { name: 'Regenerate', exact: true }).click()
  await expect.poll(() => runtime.ofType('regenerate')).toHaveLength(1)
  expect(runtime.ofType('regenerate')[0]).toMatchObject({ session_id: SESSION_ID })
  await expect(page.getByText(ORIGINAL, { exact: true })).toHaveCount(0)

  const rejection = {
    protocol_version: '2.0', type: 'protocol_error', error_code: 'regenerate_rejected',
    message: 'Regeneration refused. Please retry.', retryable: true,
    session_id: 'another-session',
  }
  runtime.send(rejection)
  // A subsequent browser task lets the incoming frame reach the session guard.
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())))
  await expect(page.getByText(rejection.message, { exact: true })).toHaveCount(0)
  await expect(page.getByText(ORIGINAL, { exact: true })).toHaveCount(0)
  runtime.send({ ...rejection, session_id: SESSION_ID })
  await expect(page.getByText(ORIGINAL, { exact: true })).toBeVisible()
  await expect(page.getByText(rejection.message, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retry', exact: true })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Stop generating', exact: true })).toHaveCount(0)
  expect(runtime.ofType('regenerate')).toHaveLength(1)
  for (const type of ['start_turn', 'submit_user_reply', 'resume_from', 'subscribe_turn'])
    expect(runtime.ofType(type)).toHaveLength(0)
})

test('mastery question survives socket replay and reload with the same answer id', async ({ page }) => {
  const question = frame('tool_result', 2, {
    metadata: { tool: 'mastery_quiz', tool_metadata: { mastery_question: {
      question_id: QUESTION_ID, prompt: QUESTION, question_type: 'single_choice',
      objective: { name: 'Thermodynamics' }, difficulty: 'easy', attempt: 1,
      options: [{ label: 'A', body: 'Disorder' }, { label: 'B', body: 'Energy' }],
      allow_free_text: false,
    } } },
  })
  let persisted = false
  const runtime = await mockRuntime(page, () => ({
    ...session(), status: persisted ? 'idle' : 'running',
    active_turns: persisted ? [] : [{ turn_id: TURN_ID }],
    messages: [session().messages[0], ...(persisted ? [{
      id: 2, parent_message_id: 1, role: 'assistant', content: '', events: [question], attachments: [],
    }] : [])],
  }))
  await page.goto(`/chat/${SESSION_ID}`)
  await expect.poll(() => runtime.ofType('subscribe_turn')).toHaveLength(1)
  expect(runtime.ofType('subscribe_turn')[0]).toMatchObject({ turn_id: TURN_ID, after_seq: 0 })
  runtime.send(frame('session', 1))
  runtime.send(question)
  await expect(page.getByText(QUESTION, { exact: true })).toHaveCount(1)
  const connectionCount = runtime.sockets.length
  runtime.sockets.at(-1)!.close({ code: 1012, reason: 'P0 reconnect exercise' })
  await expect.poll(() => runtime.sockets.length).toBeGreaterThan(connectionCount)
  await expect.poll(() => runtime.ofType('resume_from')).toContainEqual(
    expect.objectContaining({ turn_id: TURN_ID, seq: 2 }),
  )
  expect(runtime.ofType('resume_from').at(-1)).toMatchObject({ turn_id: TURN_ID })
  runtime.send(question) // Replay the last delivered event: must not duplicate the card.
  runtime.send(done())
  await expect(page.getByText(QUESTION, { exact: true })).toHaveCount(1)
  await expect(page.getByRole('button', { name: /A.*Disorder/ })).toBeEnabled()
  expect(runtime.ofType('start_turn')).toHaveLength(0)
  expect(runtime.ofType('regenerate')).toHaveLength(0)

  persisted = true
  const subscriptions = runtime.ofType('subscribe_turn').length
  await page.reload()
  await expect(page.getByText(QUESTION, { exact: true })).toHaveCount(1)
  await page.getByRole('button', { name: /A.*Disorder/ }).click()
  await page.getByRole('button', { name: 'Submit', exact: true }).click()
  await expect.poll(() => runtime.ofType('start_turn')).toHaveLength(1)
  expect(runtime.ofType('start_turn')[0]).toMatchObject({
    session_id: SESSION_ID, mastery_answer: { question_id: QUESTION_ID, text: 'A' },
  })
  expect(runtime.ofType('subscribe_turn')).toHaveLength(subscriptions)
})

test('successful regenerate replaces the answer and preserves its user attachment', async ({ page }) => {
  const runtime = await mockRuntime(page, () => ({
    ...session(), messages: [
      { ...session().messages[0], attachments: [{ type: 'file', filename: 'lecture-notes.pdf', url: '/fixture/lecture-notes.pdf' }] },
      session().messages[1],
    ],
  }))
  await openSession(page)
  await expect(page.getByRole('button', { name: 'PDF lecture-notes.pdf', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Regenerate', exact: true }).click()
  await expect.poll(() => runtime.ofType('regenerate')).toHaveLength(1)
  runtime.send(frame('session', 1))
  runtime.send(frame('content', 2, { content: REVISED }))
  runtime.send(done())
  await expect(page.getByText(REVISED, { exact: true })).toBeVisible()
  await expect(page.getByText(ORIGINAL, { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'PDF lecture-notes.pdf', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Regenerate', exact: true })).toBeEnabled()
  expect(runtime.ofType('regenerate')).toHaveLength(1)
  expect(runtime.ofType('start_turn')).toHaveLength(0)
})

test('rapid repeated regenerate clicks dispatch only one request', async ({ page }) => {
  const runtime = await mockRuntime(page)
  await openSession(page)
  const regenerate = page.getByRole('button', { name: 'Regenerate', exact: true })
  // Native clicks in one browser task exercise the state guard before React
  // can remove the control. No swallowed detached-element errors or sleeps.
  await regenerate.evaluate(button => {
    (button as HTMLButtonElement).click()
    ;(button as HTMLButtonElement).click()
  })
  await expect.poll(() => runtime.ofType('regenerate')).toHaveLength(1)
  await expect(regenerate).toHaveCount(0)
  runtime.send(frame('session', 1))
  runtime.send(frame('content', 2, { content: REVISED }))
  runtime.send(done())
  await expect(page.getByText(REVISED, { exact: true })).toBeVisible()
  await expect(regenerate).toBeEnabled()
  expect(runtime.ofType('regenerate')).toHaveLength(1)
  expect(runtime.ofType('start_turn')).toHaveLength(0)
  expect(runtime.ofType('submit_user_reply')).toHaveLength(0)
})
