// The backend answers every error in one shape (backend_spec.md, section 7):
// {"error": {"code": "task_not_found", "message": "Task 42 not found"}}
import i18n from '@/shared/i18n'

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  /** For validation errors: the names of the wrong fields. */
  readonly fields: string[]

  constructor(code: string, message: string, status: number, fields: string[] = []) {
    super(message)
    this.code = code
    this.status = status
    this.fields = fields
  }

  /** The text for people: a translation of the code if there is one,
   *  otherwise the backend's message; plus the wrong fields. */
  get text(): string {
    const text = i18n.t(`errors.${this.code}`, { defaultValue: this.message })
    if (!this.fields.length) return text
    const names = this.fields.map((f) => i18n.t(`fields.${f}`, { defaultValue: f }))
    return `${text} ${i18n.t('errors.checkFields', { fields: names.join(', ') })}`
  }
}

type Result<T> = { data?: T; error?: unknown; response: Response }

/** Return the data, or throw an ApiError. */
export async function call<T>(request: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await request
  if (response.ok) return data as T
  const body = (error ?? {}) as {
    error?: { code?: string; message?: string; details?: { loc?: unknown[] }[] }
  }
  // FastAPI validation details: loc = ["body", "email"] -> "email".
  const fields = (body.error?.details ?? [])
    .map((d) => d.loc?.at(-1))
    .filter((f): f is string => typeof f === 'string')
  throw new ApiError(
    body.error?.code ?? 'http_error',
    body.error?.message ?? response.statusText,
    response.status,
    [...new Set(fields)],
  )
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.text
  return i18n.t('errors.network')
}
