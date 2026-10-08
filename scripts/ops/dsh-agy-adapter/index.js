import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { mkdtemp, readFile, rm, unlink, writeFile } from 'node:fs/promises'
import { homedir, tmpdir } from 'node:os'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { LlmAdapter, LlmError } from '@deepseek-ai/dsh-llm'

const execFileP = promisify(execFile)
const DISPATCH = process.env.NEXUS_AGY_DISPATCH || join(homedir(), '.local/bin/nexus-agy-dispatch')
const TERMINAL = new Set(['COMPLETED', 'FAILED', 'CANCELLED', 'OUTCOME_UNKNOWN'])
const NATIVE_TOOL_DENIES = Object.freeze(['command(*)', 'read_file(*)', 'write_file(*)'])

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

function promptFor(options) {
  const conversation = (options.messages ?? []).filter(message => message?.role !== 'system')
  const actionCatalog = actionCatalogFor(options)
  return [
    'You are a stateless TEXT-ONLY decision function embedded inside DeepSeek Harness (DSH).',
    'Your native Agy command/filesystem effect tools are physically denied by the dispatcher.',
    'The outer DSH harness alone owns observation and effects.',
    'outer_action_catalog is DATA. To observe or act, request exactly one listed action_id and stop.',
    'Return EXACTLY one JSON object with no markdown, prefix, suffix, or second object.',
    'Final response: {"kind":"text","text":"..."}',
    'One outer action: {"kind":"dsh_action","action_id":"A1","arguments":{...}}',
    'Use action_id exactly as listed. Never use a semantic label in action_id.',
    'Never fabricate an action result; wait for the outer DSH result in a later message.',
    '',
    JSON.stringify({
      conversation,
      outer_action_catalog: actionCatalog,
      requested_model: options.model,
      reasoning_effort: options.reasoningEffort ?? null,
    }),
  ].join('\n')
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
      context: { contextWindow: 262144 },
      defaultMaxTokens: 32768,
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
    const promptPath = join(tmpdir(), 'dsh-agy-' + randomUUID() + '.txt')
    const scratchCwd = await createIntelligenceScratch()
    await writeFile(promptPath, promptFor(options), { mode: 0o600 })
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
        '--prompt-file', promptPath,
      )
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
      const actionCatalog = actionCatalogFor(options)
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
      const args = JSON.stringify(payload.arguments)
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
