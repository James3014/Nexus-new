import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { mkdir, mkdtemp, open, readFile, rename, rm, stat, unlink, writeFile } from 'node:fs/promises'
import { homedir, tmpdir } from 'node:os'
import { dirname, isAbsolute, join } from 'node:path'
import { createHash, randomUUID } from 'node:crypto'
import { LlmAdapter, LlmError } from '@deepseek-ai/dsh-llm'

const execFileP = promisify(execFile)
const DISPATCH = process.env.NEXUS_AGY_DISPATCH || join(homedir(), '.local/bin/nexus-agy-dispatch')
const TERMINAL = new Set(['COMPLETED', 'FAILED', 'CANCELLED', 'OUTCOME_UNKNOWN'])
const NATIVE_TOOL_DENIES = Object.freeze(['command(*)', 'read_file(*)', 'write_file(*)'])
// Transport-effective budget (#1666), not the model's native window. DSH compacts at
// floor(min(W * 0.8, W - maxTokens - 65536)) estimated tokens = 32768 here. The flattened
// Agy prompt costs ~2.0-2.3 provider tokens per DSH-estimated token, which keeps a request
// at or below ~75k provider tokens, under where Agy's own summarizer took over (~108k-116k).
const ADVERTISED_CONTEXT_WINDOW = 131072
const DEFAULT_MAX_TOKENS = 32768

function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason ?? new Error('aborted'))
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(signal.reason ?? new Error('aborted'))
    }, { once: true })
  })
}

function protocolError(message, cause) {
  return new LlmError(message, 'AGY_PROTOCOL_INVALID', cause ? { cause } : undefined)
}

const PRE_EFFECT_CODE = 'PROVIDER_PROTOCOL_INVALID_PRE_EFFECT'

// The provider response is validated before any outer action is emitted to DSH,
// so a malformed envelope here never has an effect. Surface that as a distinct
// retryable code while keeping the original code and detail visible.
function preEffectError(error) {
  const detail = String(error?.message ?? error)
  const originalCode = error?.code ?? null
  const wrapped = new LlmError(detail, PRE_EFFECT_CODE, { cause: error })
  wrapped.originalCode = originalCode
  wrapped.effect = 'none'
  wrapped.retryable = true
  return wrapped
}

// Accept exactly one JSON object, optionally wrapped in exactly one whole-response
// markdown fence. Prose around the fence or multiple fences still fail closed.
const FENCED = /^```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n?```$/i

function decodeJson(text) {
  let raw = String(text ?? '').trim()
  const fenced = FENCED.exec(raw)
  if (fenced && !fenced[1].includes('```')) raw = fenced[1].trim()
  if (!raw) throw protocolError('Agy protocol response is empty')
  let payload
  try {
    payload = JSON.parse(raw)
  } catch (error) {
    throw protocolError('Agy protocol requires exactly one JSON object', error)
  }
  if (!payload || Array.isArray(payload) || typeof payload !== 'object') {
    throw protocolError('Agy protocol payload must be one JSON object')
  }
  return payload
}

function timeoutSeconds() {
  const raw = process.env.NEXUS_DSH_AGY_TIMEOUT_SECONDS
  if (raw === undefined || raw === '') return 600
  if (!/^\d+$/.test(raw)) throw protocolError('NEXUS_DSH_AGY_TIMEOUT_SECONDS must be an integer')
  const value = Number(raw)
  if (!Number.isSafeInteger(value) || value < 30 || value > 900) {
    throw protocolError('NEXUS_DSH_AGY_TIMEOUT_SECONDS must be between 30 and 900')
  }
  return value
}

async function createIntelligenceScratch() {
  const scratch = await mkdtemp(join(tmpdir(), 'nexus-dsh-agy-intelligence-'))
  try {
    await writeFile(
      join(scratch, '.dsh-intelligence-scratch'),
      'DSH_AGY_INTELLIGENCE_NO_TARGET_EFFECTS\n',
      { mode: 0o600 },
    )
    await execFileP('git', ['init', '-q'], { cwd: scratch })
    await execFileP('git', ['add', '.dsh-intelligence-scratch'], { cwd: scratch })
    await execFileP(
      'git',
      [
        '-c', 'user.name=Nexus DSH Adapter',
        '-c', 'user.email=nexus-dsh-adapter@example.invalid',
        '-c', 'commit.gpgsign=false',
        'commit', '-qm', 'adapter baseline',
      ],
      { cwd: scratch },
    )
    return scratch
  } catch (error) {
    await rm(scratch, { recursive: true, force: true }).catch(() => {})
    throw new LlmError(
      'Failed to initialize isolated Agy intelligence workspace',
      'AGY_SCRATCH_INIT_FAILED',
      { cause: error },
    )
  }
}


function actionCatalogFor(options) {
  return (options.tools ?? []).map((tool, index) => ({
    action_id: 'A' + String(index + 1),
    semantic_label: String(tool.name ?? ''),
    purpose: typeof tool.description === 'string' ? tool.description : '',
    arguments_schema: tool.parameters,
  }))
}

function requiresDescription(entry) {
  const schema = entry.arguments_schema
  if (schema && typeof schema === 'object' && !Array.isArray(schema)) {
    const prop = schema.properties?.description
    const required = Array.isArray(schema.required) && schema.required.includes('description')
    if (prop && typeof prop === 'object' && required) {
      return prop.type === undefined || prop.type === 'string'
        || (Array.isArray(prop.type) && prop.type.includes('string'))
    }
    return false
  }
  // No schema visible: only the known bash tool gets the label-only fallback.
  return entry.semantic_label === 'bash'
}

function withRequiredDescription(entry, args) {
  if (!requiresDescription(entry)) return args
  const current = args.description
  if (typeof current === 'string' && current.trim() !== '') return args
  return { ...args, description: 'agy outer action: ' + entry.semantic_label }
}

function promptFor(options, actionCatalog) {
  const conversation = (options.messages ?? []).filter(message => message?.role !== 'system')
  const actionInstructions = actionCatalog.length > 0
    ? [
        'The following JSON object contains outer_action_catalog with every permitted outer DSH action.',
        'To observe or act, request exactly one listed action_id and stop.',
        'One outer action: {"kind":"dsh_action","action_id":"A1","arguments":{...}}',
        'Use action_id exactly as listed. Never use a semantic label in action_id.',
        'Every bash action must include a short description argument.',
        'Never fabricate an action result; wait for the outer DSH result in a later message.',
      ]
    : [
        'The following JSON object contains an empty outer_action_catalog for this internal DSH request.',
        'Return text only. Do not invent or request an outer action.',
      ]
  return [
    'You are a stateless TEXT-ONLY decision function embedded inside DeepSeek Harness (DSH).',
    'Your native Agy command/filesystem effect tools are physically denied by the dispatcher.',
    'The outer DSH harness alone owns observation and effects.',
    ...actionInstructions,
    'Return EXACTLY one JSON object with no markdown, prefix, suffix, or second object.',
    'Final response: {"kind":"text","text":"..."}',
    '',
    JSON.stringify({
      conversation,
      outer_action_catalog: actionCatalog,
      request_purpose: options.purpose ?? null,
      requested_model: options.model,
      reasoning_effort: options.reasoningEffort ?? null,
    }),
  ].join('\n')
}

function actionContractEvidence(actionCatalog, prompt) {
  const catalogJson = JSON.stringify(actionCatalog)
  const catalogSha256 = createHash('sha256').update(catalogJson).digest('hex')
  return [
    'dsh_action_contract:v1',
    'catalog_count=' + String(actionCatalog.length),
    'catalog_sha256=' + catalogSha256,
    'prompt_chars=' + String(prompt.length),
    'context_window=' + String(ADVERTISED_CONTEXT_WINDOW),
  ].join(':')
}

function validatedEffort(model, value) {
  if (value === undefined || value === null || value === '') return null
  if (value !== 'low' && value !== 'medium' && value !== 'high') {
    throw protocolError('Unsupported reasoning effort: ' + String(value))
  }
  const suffix = String(model).match(/-(low|medium|high)$/)?.[1] ?? null
  if (suffix !== null && value !== suffix) {
    throw protocolError(
      'Model/effort contract mismatch: ' + String(model) + ' requires ' + suffix,
    )
  }
  return value
}

const PROVIDER_CALL_CAP_CODE = 'AGY_PROVIDER_CALL_CAP_EXHAUSTED'

// Opt-in cap on physical dispatches; unset keeps the existing unlimited behavior.
function providerCallCap() {
  const raw = process.env.NEXUS_DSH_AGY_MAX_PROVIDER_CALLS
  if (raw === undefined || raw === '') return null
  if (!/^\d+$/.test(raw)) throw protocolError('NEXUS_DSH_AGY_MAX_PROVIDER_CALLS must be an integer')
  const value = Number(raw)
  if (!Number.isSafeInteger(value) || value < 1 || value > 64) {
    throw protocolError('NEXUS_DSH_AGY_MAX_PROVIDER_CALLS must be between 1 and 64')
  }
  return value
}

const OPERATION_MARKER_SCHEMA = 'nexus.dsh_agy_operation_marker.v1'

const BUDGET_SCHEMA = 'nexus.dsh_agy_provider_budget.v1'

const BUDGET_STATE_INVALID_CODE = 'AGY_PROVIDER_BUDGET_STATE_INVALID'

const BUDGET_LOCK_WAIT_MS = 2000

const SESSION_ID_PATTERN = /^[A-Za-z0-9_.:-]{1,128}$/

const BUDGET_PURPOSES = new Set(['agent', 'compaction', 'session-title'])

function budgetError(code, message, cause) {
  const error = new LlmError(message, code, cause ? { cause } : undefined)
  error.effect = 'none'
  error.retryable = false
  return error
}

// DSH's own call-slot policy state (counts only, no prompts or Agy results).
function budgetDir() {
  const raw = process.env.NEXUS_DSH_AGY_BUDGET_DIR
  if (raw === undefined || raw === '') return join(homedir(), '.local/state/nexus-dsh-agy-budget')
  if (!isAbsolute(raw)) throw protocolError('NEXUS_DSH_AGY_BUDGET_DIR must be an absolute path')
  return raw
}

function budgetRecordPath(dir, sessionId) {
  return join(dir, createHash('sha256').update(sessionId).digest('hex') + '.json')
}

async function readBudgetRecord(path) {
  let raw
  try {
    raw = await readFile(path, 'utf8')
  } catch (error) {
    if (error?.code === 'ENOENT') return null
    throw budgetError(BUDGET_STATE_INVALID_CODE, 'Agy provider budget record is unreadable')
  }
  let record
  try {
    record = JSON.parse(raw)
  } catch {
    throw budgetError(BUDGET_STATE_INVALID_CODE, 'Agy provider budget record is not JSON')
  }
  const valid = record !== null && typeof record === 'object' && !Array.isArray(record)
    && record.schema === BUDGET_SCHEMA
    && Number.isSafeInteger(record.limit) && record.limit >= 1
    && Number.isSafeInteger(record.used) && record.used >= 0 && record.used <= record.limit
    && record.purposes !== null && typeof record.purposes === 'object' && !Array.isArray(record.purposes)
  if (!valid || !purposesConsistent(record)) {
    throw budgetError(BUDGET_STATE_INVALID_CODE, 'Agy provider budget record is malformed')
  }
  return record
}

// Every purpose counter is a non-negative integer under a known key, and they sum to `used`.
function purposesConsistent(record) {
  const entries = Object.entries(record.purposes)
  const known = entries.every(([key, count]) =>
    (BUDGET_PURPOSES.has(key) || key === 'other') && Number.isSafeInteger(count) && count >= 0)
  const sum = entries.reduce((total, [, count]) => total + (known ? count : 0), 0)
  return known && sum === record.used
}

async function writeBudgetRecord(path, record) {
  const tmp = path + '.' + randomUUID() + '.tmp'
  try {
    const handle = await open(tmp, 'wx', 0o600)
    try {
      await handle.writeFile(JSON.stringify(record) + '\n')
      await handle.sync()
    } finally {
      await handle.close()
    }
    await rename(tmp, path)
  } catch (error) {
    await unlink(tmp).catch(() => {})
    throw budgetError('AGY_PROVIDER_BUDGET_PERSIST_FAILED', 'Agy provider budget reservation was not persisted; no dispatch was made', error)
  }
  // Directory fsync makes the rename durable before the physical dispatch is allowed.
  try {
    const dirHandle = await open(dirname(path), 'r')
    try {
      await dirHandle.sync()
    } finally {
      await dirHandle.close()
    }
  } catch (error) {
    throw budgetError('AGY_PROVIDER_BUDGET_PERSIST_FAILED', 'Agy provider budget directory fsync failed; no dispatch was made', error)
  }
}

// Only ENOENT means "no policy directory". Any other stat failure, or a non-directory
// at the policy path, is ambiguous state and must fail closed rather than read as unlimited.
async function budgetDirExists(dir) {
  let entry
  try {
    entry = await stat(dir)
  } catch (error) {
    if (error?.code === 'ENOENT') return false
    throw budgetError(BUDGET_STATE_INVALID_CODE, 'Agy provider budget directory is unreadable; failing closed', error)
  }
  if (!entry.isDirectory()) throw budgetError(BUDGET_STATE_INVALID_CODE, 'Agy provider budget path is not a directory')
  return true
}

// Exclusive pre-effect lock. A stale lock fails closed; it is never stolen.
async function acquireBudgetLock(recordPath) {
  const lockPath = recordPath.replace(/\.json$/, '.lock')
  const deadline = Date.now() + BUDGET_LOCK_WAIT_MS
  for (;;) {
    try {
      const handle = await open(lockPath, 'wx', 0o600)
      await handle.close()
      return lockPath
    } catch (error) {
      if (error?.code !== 'EEXIST') throw budgetError(BUDGET_STATE_INVALID_CODE, 'Agy provider budget lock is unavailable')
      if (Date.now() >= deadline) {
        throw budgetError('AGY_PROVIDER_BUDGET_LOCK_TIMEOUT', 'Agy provider budget lock is held; failing closed without stealing it')
      }
      await delay(20)
    }
  }
}

// Canonical binding of one dispatch to its DSH session: a sha256 of the session id and a
// validated purpose label. The raw session id never leaves the process. Returns null when
// the session or purpose cannot be validated, so the phase report fails closed.
function dshSessionEvidence(options) {
  if (typeof options.sessionId !== 'string' || !SESSION_ID_PATTERN.test(options.sessionId)) return null
  const purpose = options.purpose ?? 'agent'
  if (!BUDGET_PURPOSES.has(purpose)) return null
  const digest = createHash('sha256').update(options.sessionId).digest('hex')
  return 'dsh_session:v1:session_sha256=' + digest + ':purpose=' + purpose
}

// Reserve one physical call slot durably before any dispatch. Unknown or failed
// physical calls keep their reservation, so a retry cannot escape the cap.
async function reserveProviderCall(options) {
  const cap = providerCallCap()
  const sessionId = options.sessionId
  const hasIdentity = typeof sessionId === 'string' && SESSION_ID_PATTERN.test(sessionId)
  if (cap === null) {
    // No policy directory means no capped session can exist: legacy unlimited, no writes.
    if (!hasIdentity || !(await budgetDirExists(budgetDir()))) return
    const path = budgetRecordPath(budgetDir(), sessionId)
    const lock = await acquireBudgetLock(path)
    try {
      if ((await readBudgetRecord(path)) !== null) {
        throw budgetError('AGY_PROVIDER_BUDGET_CAP_REMOVED', 'Agy provider budget exists for this session; the cap cannot be removed')
      }
    } finally {
      await unlink(lock).catch(() => {})
    }
    return
  }
  if (!hasIdentity) {
    throw budgetError('AGY_PROVIDER_BUDGET_SESSION_REQUIRED', 'Capped Agy calls require a valid DSH session identity')
  }
  const dir = budgetDir()
  await mkdir(dir, { recursive: true, mode: 0o700 })
  const path = budgetRecordPath(dir, sessionId)
  const lock = await acquireBudgetLock(path)
  try {
    const record = (await readBudgetRecord(path)) ?? { schema: BUDGET_SCHEMA, limit: cap, used: 0, purposes: {} }
    if (record.limit !== cap) {
      throw budgetError('AGY_PROVIDER_BUDGET_CAP_MISMATCH', 'Agy provider budget limit differs from the recorded session cap')
    }
    if (record.used >= record.limit) {
      throw budgetError(PROVIDER_CALL_CAP_CODE, 'Agy provider call cap ' + String(cap) + ' exhausted for this DSH session; no further physical provider call')
    }
    record.used += 1
    const purpose = options.purpose ?? 'agent'
    const key = BUDGET_PURPOSES.has(purpose) ? purpose : 'other'
    record.purposes[key] = (record.purposes[key] ?? 0) + 1
    await writeBudgetRecord(path, record)
  } finally {
    await unlink(lock).catch(() => {})
  }
}

export class AgyPoolAdapter extends LlmAdapter {
  providerInfo(provider) {
    return { id: provider, name: 'Nexus Agy Pool' }
  }

  providerRetryPolicy() {
    return Object.freeze({
      mode: 'normal',
      maxRetries: 0,
      retryableCodes: Object.freeze(['NEXUS_NO_AUTORETRY']),
      initialDelayMs: 500,
      maxDelayMs: 500,
      jitterRatio: 0,
    })
  }

  async listModels(provider) {
    return [
      'gemini-3.8-flash-low',
      'gemini-3.8-flash-medium',
      'gemini-3.8-flash-high',
      'gemini-3.7-flash-low',
      'gemini-3.7-flash-medium',
      'gemini-3.7-flash-high',
      'gemini-3.6-flash-low',
      'gemini-3.6-flash-medium',
      'gemini-3.6-flash-high',
      'gemini-3.1-pro-low',
      'gemini-3.1-pro-high',
    ].map(id => ({ provider, id, name: id, inputModalities: ['text'] }))
  }

  async resolveModel(provider, model) {
    const info = {
      provider,
      id: model,
      name: model,
      inputModalities: ['text'],
      context: { contextWindow: ADVERTISED_CONTEXT_WINDOW },
      defaultMaxTokens: DEFAULT_MAX_TOKENS,
    }
    if (model.startsWith('gemini-')) {
      info.reasoning = {
        efforts: [
          { id: 'low', name: 'Low' },
          { id: 'medium', name: 'Medium' },
          { id: 'high', name: 'High' },
        ],
        defaultEffort: model.endsWith('-high') ? 'high' : model.endsWith('-medium') ? 'medium' : 'low',
      }
    }
    return info
  }

  async *stream(options) {
    const actionCatalog = actionCatalogFor(options)
    const internalPurpose = options.purpose === 'compaction' || options.purpose === 'session-title'
    if (!internalPurpose && actionCatalog.length === 0) {
      // Config/contract error, not a provider-protocol error: fail closed pre-dispatch.
      throw new LlmError(
        'Normal DSH agent turn reached Agy adapter without an outer action catalog',
        'AGY_OUTER_ACTION_CATALOG_EMPTY',
      )
    }
    const prompt = promptFor(options, actionCatalog)
    const evidenceRef = actionContractEvidence(actionCatalog, prompt)
    const promptPath = join(tmpdir(), 'dsh-agy-' + randomUUID() + '.txt')
    const scratchCwd = await createIntelligenceScratch()
    await writeFile(promptPath, prompt, { mode: 0o600 })
    let started
    try {
      const argv = [
        '--background',
        '--cwd', scratchCwd,
        '--mode', 'plan',
        '--model', options.model,
      ]
      const effort = validatedEffort(options.model, options.reasoningEffort)
      if (effort !== null) argv.push('--effort', effort)
      for (const rule of NATIVE_TOOL_DENIES) argv.push('--deny', rule)
      argv.push(
        '--timeout', String(timeoutSeconds()),
        '--max-calls', '1',
        '--evidence-ref', evidenceRef,
        '--prompt-file', promptPath,
      )
      const sessionRef = dshSessionEvidence(options)
      if (sessionRef !== null) argv.push('--evidence-ref', sessionRef)
      // Reserve the physical call slot durably before any dispatch.
      await reserveProviderCall(options)
      const { stdout } = await execFileP(DISPATCH, argv, { maxBuffer: 4 * 1024 * 1024 })
      started = JSON.parse(stdout)
    } catch (error) {
      await rm(scratchCwd, { recursive: true, force: true }).catch(() => {})
      if (error instanceof LlmError) throw error
      throw new LlmError(
        'Agy dispatch did not start: ' + String(error),
        'AGY_DISPATCH_START_FAILED',
        { cause: error },
      )
    } finally {
      await unlink(promptPath).catch(() => {})
    }

    const operationId = started?.operation_id
    if (typeof operationId !== 'string' || operationId.length === 0) {
      await rm(scratchCwd, { recursive: true, force: true }).catch(() => {})
      throw new LlmError('Agy dispatch returned no operation id', 'AGY_OPERATION_ID_MISSING')
    }
    // Non-secret correlation marker for the phase log: the exact DSH session, the canonical
    // operation id and the purpose. Never the prompt, the account or a provider result.
    process.stderr.write('NEXUS_DSH_AGY_OPERATION ' + JSON.stringify({
      schema: OPERATION_MARKER_SCHEMA,
      dsh_session_id: options.sessionId ?? null,
      operation_id: operationId,
      purpose: options.purpose ?? 'agent',
    }) + '\n')

    let record = started
    while (!TERMINAL.has(record?.status)) {
      try {
        await delay(350, options.signal)
      } catch (error) {
        throw new LlmError(
          'DSH request aborted while Agy operation remains governed as ' + operationId,
          'AGY_OPERATION_ABORTED',
          { cause: error },
        )
      }
      const { stdout } = await execFileP(
        DISPATCH,
        ['--status', operationId],
        { maxBuffer: 4 * 1024 * 1024 },
      )
      record = JSON.parse(stdout)
    }

    if (record.status === 'OUTCOME_UNKNOWN') {
      throw new LlmError(
        'Agy outcome unknown; reconcile exact operation ' + operationId
          + ' before retry; preserved scratch=' + scratchCwd,
        'AGY_OUTCOME_UNKNOWN',
      )
    }
    if (record.status !== 'COMPLETED') {
      await rm(scratchCwd, { recursive: true, force: true }).catch(() => {})
      throw new LlmError(
        'Agy operation ' + operationId + ' ended as ' + String(record.status)
          + (record.failure_kind ? ' (' + record.failure_kind + ')' : ''),
        'AGY_OPERATION_FAILED',
      )
    }

    let rawPayload
    try {
      rawPayload = await readFile(record.stdout_path, 'utf8')
    } finally {
      await rm(scratchCwd, { recursive: true, force: true }).catch(() => {})
    }
    let payload
    try {
      payload = decodeJson(rawPayload)
    } catch (error) {
      throw preEffectError(error)
    }
    if (payload.kind === 'dsh_action') {
      let entry = actionCatalog.find(item => item.action_id === payload.action_id)
      if (!entry && typeof payload.action_id === 'string') {
        // Observed: the model sometimes puts the semantic label ("bash") in
        // action_id. Accept only an exact, case-sensitive label that maps to
        // exactly one catalog entry; anything else stays unavailable.
        const byLabel = actionCatalog.filter(
          item => item.semantic_label && item.semantic_label === payload.action_id,
        )
        if (byLabel.length === 1) entry = byLabel[0]
      }
      if (!entry || !entry.semantic_label) {
        throw preEffectError(new LlmError(
          'Agy requested unavailable DSH action: ' + String(payload.action_id),
          'AGY_TOOL_NOT_AVAILABLE',
        ))
      }
      if (!payload.arguments || Array.isArray(payload.arguments) || typeof payload.arguments !== 'object') {
        throw preEffectError(protocolError('Agy outer action arguments must be a JSON object'))
      }
      const args = JSON.stringify(withRequiredDescription(entry, payload.arguments))
      const id = 'agy-call-' + randomUUID()
      yield { type: 'block-start', index: 0, blockType: 'tool-call' }
      yield { type: 'tool-call-delta', index: 0, id, name: entry.semantic_label, argumentsDelta: args }
      yield {
        type: 'block-end',
        index: 0,
        block: { type: 'tool-call', id, name: entry.semantic_label, arguments: args },
      }
      yield { type: 'finish', reason: { kind: 'tool-calls' } }
      return
    }

    if (payload.kind !== 'text' || typeof payload.text !== 'string') {
      throw preEffectError(protocolError('Agy protocol requires kind=text or kind=dsh_action'))
    }
    yield { type: 'block-start', index: 0, blockType: 'text' }
    if (payload.text.length > 0) yield { type: 'text-delta', index: 0, text: payload.text }
    yield { type: 'block-end', index: 0, block: { type: 'text', text: payload.text } }
    yield { type: 'finish', reason: { kind: 'stop' } }
  }
}

export const name = 'nexus-agy-pool-llm'
export const inject = ['llm']

export function apply(ctx) {
  ctx.llm.registerAdapter(['nexus-agy-pool'], new AgyPoolAdapter())
}
