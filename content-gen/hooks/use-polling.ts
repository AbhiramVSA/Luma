"use client"

import { useEffect, useRef, useCallback } from "react"

interface UsePollingOptions {
  interval?: number
  maxAttempts?: number
  onSuccess?: (data: any) => void
  onError?: (error: Error) => void
  onComplete?: () => void
}

/**
 * Custom hook for polling API endpoints
 */
export function usePolling(
  fetchFn: () => Promise<any>,
  shouldContinue: (data: any) => boolean,
  options: UsePollingOptions = {},
) {
  const { interval = 5000, maxAttempts = Number.POSITIVE_INFINITY, onSuccess, onError, onComplete } = options

  const attemptsRef = useRef(0)
  const intervalRef = useRef<NodeJS.Timeout | null>(null)

  const startPolling = useCallback(() => {
    attemptsRef.current = 0

    const poll = async () => {
      try {
        const data = await fetchFn()
        onSuccess?.(data)

        if (!shouldContinue(data)) {
          stopPolling()
          onComplete?.()
        } else {
          attemptsRef.current++
          if (attemptsRef.current >= maxAttempts) {
            stopPolling()
            onComplete?.()
          }
        }
      } catch (error) {
        onError?.(error instanceof Error ? error : new Error("Polling error"))
      }
    }

    poll()
    intervalRef.current = setInterval(poll, interval)
  }, [fetchFn, shouldContinue, interval, maxAttempts, onSuccess, onError, onComplete])

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  useEffect(() => {
    return () => stopPolling()
  }, [stopPolling])

  return { startPolling, stopPolling }
}

/**
 * Custom hook for exponential backoff polling
 */
export function useExponentialBackoffPolling(
  fetchFn: () => Promise<any>,
  shouldContinue: (data: any) => boolean,
  options: UsePollingOptions & { baseInterval?: number; maxInterval?: number } = {},
) {
  const {
    baseInterval = 1000,
    maxInterval = 30000,
    maxAttempts = Number.POSITIVE_INFINITY,
    onSuccess,
    onError,
    onComplete,
  } = options

  const attemptsRef = useRef(0)
  const intervalRef = useRef<NodeJS.Timeout | null>(null)

  const startPolling = useCallback(() => {
    attemptsRef.current = 0

    const poll = async () => {
      try {
        const data = await fetchFn()
        onSuccess?.(data)

        if (!shouldContinue(data)) {
          stopPolling()
          onComplete?.()
        } else {
          attemptsRef.current++
          if (attemptsRef.current >= maxAttempts) {
            stopPolling()
            onComplete?.()
          } else {
            const nextInterval = Math.min(baseInterval * Math.pow(2, attemptsRef.current), maxInterval)
            intervalRef.current = setTimeout(poll, nextInterval)
          }
        }
      } catch (error) {
        onError?.(error instanceof Error ? error : new Error("Polling error"))
      }
    }

    poll()
  }, [fetchFn, shouldContinue, baseInterval, maxInterval, maxAttempts, onSuccess, onError, onComplete])

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearTimeout(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  useEffect(() => {
    return () => stopPolling()
  }, [stopPolling])

  return { startPolling, stopPolling }
}
