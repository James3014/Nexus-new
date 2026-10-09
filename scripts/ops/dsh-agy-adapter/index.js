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
const ADVERTISED_CONTEXT_WINDOW = 262144
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

function boundedEnvInt(name, fallback, min, max) {
  const raw = process.env[name]
  if (raw === undefined || raw === '') return fallback
  if (!/^\d+$/.test(raw)) throw protocolError(name + ' must be an integer')
  const value = Number(raw)
  if (!Number.isSafeInteger(value) || value < min || value > max) {
    throw protocolError(name + ' must be between ' + String(min) + ' and ' + String(max))
  }
  return value
}

const POOL_BUSY_CODE = 'AGY_ACCOUNT_POOL_BUSY_PRE_EFFECT'
const QUOTA_PRE_EFFECT_CODE = 'PROVIDER_QUOTA_EXHAUSTED_PRE_EFFECT'
const RETRYABLE_PRE_EFFECT_CODES = new Set([PRE_EFFECT_CODE, POOL_BUSY_CODE, QUOTA_PRE_EFFECT_CODE])
const DEFAULT_RETRY_BACKOFF_MS = Object.freeze([10000, 30000])
const DISPATCH_META_PREFIX = 'NEXUS_AGY_DISPATCH '
const DISPATCH_STDERR_MAX_BYTES = 4 * 1024 * 1024

function preEffectRetries() {
  return boundedEnvInt('NEXUS_DSH_AGY_PRE_EFFECT_RETRIES', 2, 0, 3)
}

function poolWaitSeconds() {
  return boundedEnvInt('NEXUS_DSH_AGY_POOL_WAIT_SECONDS', 120, 15, 600)
}

// Optional override (tests/operators) of the 10s/30s backoff, still bounded to 30s per wait.
function retryBackoffMs() {
  const raw = process.env.NEXUS_DSH_AGY_RETRY_BACKOFF_MS
  if (raw === undefined || raw === '') return DEFAULT_RETRY_BACKOFF_MS
  const parts = raw.split(',').map(part => part.trim())
  const valid = parts.length >= 1 && parts.length <= 3
    && parts.every(part => /^\d+$/.test(part) && Number(part) <= 30000)
  if (!valid) throw protocolError('NEXUS_DSH_AGY_RETRY_BACKOFF_MS must be 1-3 integers between 0 and 30000')
  return parts.map(Number)
}

// The record carries explicit evidence that the operation produced no effect.
// A missing key is not proof; any recorded effect or changed path excludes retry.
function recordProvesNoEffect(record) {
  if (!record || typeof record !== 'object') return false
  if (record.first_effect_at !== null) return false
  // Any contradictory effect evidence in the same record fails closed.
  if (record.provider_effect === true || record.has_unresolved_external_effect === true) return false
  if (typeof record.scope_validation_state === 'string' && record.scope_validation_state.startsWith('VIOLATION')) return false
  const changed = record.observed_changed_paths
  if (changed !== null && changed !== undefined && !(Array.isArray(changed) && changed.length === 0)) return false
  const reconciliation = record.reconciliation
  return !(reconciliation && typeof reconciliation === 'object' && reconciliation.retry_permitted === false)
}

// The canonical dispatcher writes `NEXUS_AGY_DISPATCH {json}` to the operation stderr.
// Returns the last meta object, or null when absent, unreadable or any meta line is malformed.
async function readDispatchMeta(stderrPath) {
  if (typeof stderrPath !== 'string' || !isAbsolute(stderrPath)) return null
  let text
  try {
    if ((await stat(stderrPath)).size > DISPATCH_STDERR_MAX_BYTES) return null
    text = await readFile(stderrPath, 'utf8')
  } catch {
    return null
  }
  let meta = null
  for (const line of text.split(/\r?\n/)) {
    if (!line.startsWith(DISPATCH_META_PREFIX)) continue
    try {
      meta = JSON.parse(line.slice(DISPATCH_META_PREFIX.length))
    } catch {
      return null
    }
    if (!meta || typeof meta !== 'object' || Array.isArray(meta)) return null
  }
  return meta
}

function describeMeta(meta) {
  if (!meta) return ''
  const parts = ['status', 'failure_kind', 'reason']
    .filter(key => typeof meta[key] === 'string' && meta[key] !== '')
    .map(key => key + '=' + meta[key])
  return parts.length > 0 ? ' [dispatch ' + parts.join(', ') + ']' : ''
}

// Typed pre-effect error for a FAILED operation, or null unless the record and the
// dispatcher meta both prove that no provider effect occurred.
function classifyFailedOperation(record, meta, operationId) {
  if (record?.status !== 'FAILED' || !recordProvesNoEffect(record)) return null
  if (!meta || meta.provider_effect !== false) return null
  const kind = meta.failure_kind
  if (record.failure_kind !== null && record.failure_kind !== undefined && record.failure_kind !== kind) return null
  let code
  let detail
  if (meta.status === 'pool_busy' && kind === 'AGY_ACCOUNT_POOL_BUSY') {
    code = POOL_BUSY_CODE
    detail = 'Agy account pool busy (no free lease slot) before any provider effect'
  } else if (kind === QUOTA_PRE_EFFECT_CODE) {
    code = QUOTA_PRE_EFFECT_CODE
    detail = 'Agy provider quota exhausted before any provider effect'
  } else {
    return null
  }
  const error = new LlmError(detail + '; operation ' + operationId + ' FAILED', code)
  error.effect = 'none'
  error.retryable = true
  error.failureKind = kind
  error.operationId = operationId
  return error
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
    const maxRetries = preEffectRetries()
    const backoff = retryBackoffMs()
    const poolWait = poolWaitSeconds()
    let events
    for (let attempt = 1; ; attempt += 1) {
      try {
        events = await this.runAttempt(options, actionCatalog, poolWait)
        break
      } catch (error) {
        if (error && typeof error === 'object') error.attempts = attempt
        // Only provably pre-effect failures get a new canonical operation; every attempt
        // reserves its own budget slot, so retries cannot bypass the session cap.
        const retryable = RETRYABLE_PRE_EFFECT_CODES.has(error?.code)
          && error?.effect === 'none'
          && attempt <= maxRetries
        if (!retryable) throw error
        try {
          await delay(backoff[Math.min(attempt - 1, backoff.length - 1)], options.signal)
        } catch (abortError) {
          throw new LlmError(
            'DSH request aborted during Agy pre-effect retry backoff',
            'AGY_OPERATION_ABORTED',
            { cause: abortError },
          )
        }
      }
    }
    yield* events
  }

  // One physical provider step. The response is validated and projected before any
  // event is returned, so a thrown error never follows an emitted outer action.
  async runAttempt(options, actionCatalog, poolWait) {
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
        '--pool-wait-timeout', String(poolWait),
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
      const meta = await readDispatchMeta(record.stderr_path)
      throw classifyFailedOperation(record, meta, operationId) ?? new LlmError(
        'Agy operation ' + operationId + ' ended as ' + String(record.status)
          + (record.failure_kind ? ' (' + record.failure_kind + ')' : '') + describeMeta(meta),
        'AGY_OPERATION_FAILED',
      )
    }

    let rawPayload
    try {
      rawPayload = await readFile(record.stdout_path, 'utf8')
    } finally {
      await rm(scratchCwd, { recursive: true, force: true }).catch(() => {})
    }
    const noEffect = recordProvesNoEffect(record)
    const invalid = error => {
      if (noEffect) return preEffectError(error)
      // A recorded or unprovable effect excludes the pre-effect retry class.
      const wrapped = new LlmError(
        String(error?.message ?? error) + '; operation ' + operationId + ' has no proof of zero effect',
        'PROVIDER_PROTOCOL_INVALID_EFFECT_UNPROVEN',
        { cause: error },
      )
      wrapped.originalCode = error?.code ?? null
      wrapped.effect = 'unknown'
      wrapped.retryable = false
      return wrapped
    }
    let payload
    try {
      payload = decodeJson(rawPayload)
    } catch (error) {
      throw invalid(error)
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
        throw invalid(new LlmError(
          'Agy requested unavailable DSH action: ' + String(payload.action_id),
          'AGY_TOOL_NOT_AVAILABLE',
        ))
      }
      if (!payload.arguments || Array.isArray(payload.arguments) || typeof payload.arguments !== 'object') {
        throw invalid(protocolError('Agy outer action arguments must be a JSON object'))
      }
      const args = JSON.stringify(withRequiredDescription(entry, payload.arguments))
      const id = 'agy-call-' + randomUUID()
      return [
        { type: 'block-start', index: 0, blockType: 'tool-call' },
        { type: 'tool-call-delta', index: 0, id, name: entry.semantic_label, argumentsDelta: args },
        {
          type: 'block-end',
          index: 0,
          block: { type: 'tool-call', id, name: entry.semantic_label, arguments: args },
        },
        { type: 'finish', reason: { kind: 'tool-calls' } },
      ]
    }

    if (payload.kind !== 'text' || typeof payload.text !== 'string') {
      throw invalid(protocolError('Agy protocol requires kind=text or kind=dsh_action'))
    }
    const events = [{ type: 'block-start', index: 0, blockType: 'text' }]
    if (payload.text.length > 0) events.push({ type: 'text-delta', index: 0, text: payload.text })
    events.push(
      { type: 'block-end', index: 0, block: { type: 'text', text: payload.text } },
      { type: 'finish', reason: { kind: 'stop' } },
    )
    return events
  }
}

export const name = 'nexus-agy-pool-llm'
export const inject = ['llm']

export function apply(ctx) {
  ctx.llm.registerAdapter(['nexus-agy-pool'], new AgyPoolAdapter())
}
