/** API / WebSocket base URLs — production uses same-origin relative paths for Docker. */
const trimSlash = (value: string) => value.replace(/\/$/, '')

const configuredApi = import.meta.env.VITE_API_BASE_URL as string | undefined

export const API_BASE_URL = trimSlash(
  configuredApi || (import.meta.env.DEV ? 'http://localhost:8000/api/v1' : '/api/v1')
)

export function apiUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${normalized}`
}

export function wsUrl(path: string): string {
  const configuredWs = import.meta.env.VITE_WS_BASE_URL as string | undefined
  const normalized = path.startsWith('/') ? path : `/${path}`

  if (configuredWs) {
    return `${trimSlash(configuredWs)}${normalized}`
  }

  if (import.meta.env.DEV) {
    return `ws://localhost:8000/api/v1${normalized}`
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/v1${normalized}`
}
