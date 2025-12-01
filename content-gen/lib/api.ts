export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8002/api/v1"
export const API_ORIGIN = process.env.NEXT_PUBLIC_API_ORIGIN ?? API_BASE_URL.replace(/\/api\/v1$/, "")
export const TOKEN_STORAGE_KEY = "innerbhakti.auth.token"

export const buildApiUrl = (path: string) => {
  if (!path) return API_BASE_URL
  if (path.startsWith("http")) {
    return path
  }
  const normalized = path.startsWith("/") ? path : `/${path}`
  return `${API_BASE_URL}${normalized}`
}

export const apiAssetUrl = (path: string | null | undefined) => {
  if (!path) return ""
  if (path.startsWith("http")) {
    return path
  }
  const normalized = path.startsWith("/") ? path : `/${path}`
  return `${API_ORIGIN}${normalized}`
}

export const getAuthToken = () => {
  if (typeof window === "undefined") {
    return null
  }
  return window.localStorage.getItem(TOKEN_STORAGE_KEY)
}

export const setAuthToken = (token: string) => {
  if (typeof window === "undefined") {
    return
  }
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token)
}

export const clearAuthToken = () => {
  if (typeof window === "undefined") {
    return
  }
  window.localStorage.removeItem(TOKEN_STORAGE_KEY)
}

const buildAuthHeader = () => {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export const apiFetch = (path: string, init: RequestInit = {}) => {
  const url = buildApiUrl(path)
  const headers = new Headers(init.headers ?? {})
  const authHeader = buildAuthHeader()
  if (authHeader.Authorization && !headers.has("Authorization")) {
    headers.set("Authorization", authHeader.Authorization)
  }
  return fetch(url, {
    ...init,
    headers,
  })
}
