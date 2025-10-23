/**
 * Centralized error handling for the application
 */

export class ApiError extends Error {
  constructor(
    public statusCode: number,
    public message: string,
    public details?: any,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

export class ValidationError extends Error {
  constructor(public message: string) {
    super(message)
    this.name = "ValidationError"
  }
}

export class TimeoutError extends Error {
  constructor(public message = "Request timeout") {
    super(message)
    this.name = "TimeoutError"
  }
}

/**
 * Parse API error response
 */
export function parseApiError(error: any): string {
  if (error instanceof ApiError) {
    return error.message
  }

  if (error instanceof ValidationError) {
    return error.message
  }

  if (error instanceof TimeoutError) {
    return error.message
  }

  if (error?.response?.data?.detail) {
    return error.response.data.detail
  }

  if (error?.message) {
    return error.message
  }

  return "An unexpected error occurred. Please try again."
}

/**
 * Handle fetch errors with timeout
 */
export async function fetchWithTimeout(
  url: string,
  options: RequestInit & { timeout?: number } = {},
): Promise<Response> {
  const { timeout = 30000, ...fetchOptions } = options

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new ApiError(response.status, data.detail || `HTTP ${response.status}`, data)
    }

    return response
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new TimeoutError()
    }
    throw error
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Retry logic for failed requests
 */
export async function retryRequest<T>(fn: () => Promise<T>, maxRetries = 3, delayMs = 1000): Promise<T> {
  let lastError: Error | null = null

  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn()
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error))

      if (i < maxRetries - 1) {
        await new Promise((resolve) => setTimeout(resolve, delayMs * Math.pow(2, i)))
      }
    }
  }

  throw lastError
}
