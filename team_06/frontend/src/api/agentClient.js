const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, '')
const SESSION_KEY = 'inhabit-session-id'

function getSessionId() {
  let sessionId = window.sessionStorage.getItem(SESSION_KEY)
  if (!sessionId) {
    sessionId = crypto.randomUUID()
    window.sessionStorage.setItem(SESSION_KEY, sessionId)
  }
  return sessionId
}

function setSessionId(sessionId) {
  if (sessionId) window.sessionStorage.setItem(SESSION_KEY, sessionId)
}

function resetSessionId() {
  const sessionId = crypto.randomUUID()
  window.sessionStorage.setItem(SESSION_KEY, sessionId)
  return sessionId
}

export async function startFreshSession() {
  const existingSessionId = window.sessionStorage.getItem(SESSION_KEY)
  if (existingSessionId) {
    try {
      await request('/session', {
        method: 'DELETE',
        body: JSON.stringify({ session_id: existingSessionId })
      })
    } catch {
      // Ignore stale backend cleanup failures and still rotate the local session id.
    }
  }

  resetSessionId()
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {})
    },
    ...options
  })

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const payload = await response.json()
      detail = payload.detail || payload.message || detail
    } catch {
      // Keep default detail.
    }
    throw new Error(detail)
  }

  if (response.status === 204) return null
  return response.json()
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

export async function sendChatMessage(message, onStatusUpdate) {
  const startPayload = await request('/chat/start', {
    method: 'POST',
    body: JSON.stringify({
      session_id: getSessionId(),
      message
    })
  })
  setSessionId(startPayload.session_id)

  let lastStatusKey = ''
  while (true) {
    const statusPayload = await request(`/chat/status/${getSessionId()}`, {
      method: 'GET'
    })

    const statusMessages = statusPayload.status_messages ?? []
    const statusKey = JSON.stringify(statusMessages)
    if (statusKey !== lastStatusKey) {
      lastStatusKey = statusKey
      onStatusUpdate?.(statusMessages)
    }

    if (statusPayload.status === 'completed') {
      return statusPayload.result
    }

    if (statusPayload.status === 'failed') {
      throw new Error(statusPayload.error || 'Chat request failed')
    }

    await sleep(400)
  }
}

export async function uploadBoundaryLayout(layout) {
  const payload = await request('/upload-layout', {
    method: 'POST',
    body: JSON.stringify({
      session_id: getSessionId(),
      layout_json: layout ? JSON.stringify(layout) : null
    })
  })
  setSessionId(payload.session_id)
  return payload
}

export async function restoreLayout(layout) {
  return request('/restore-layout', {
    method: 'POST',
    body: JSON.stringify({
      session_id: getSessionId(),
      layout_json: JSON.stringify(layout)
    })
  })
}

export async function clearSession() {
  const sessionId = getSessionId()
  await request('/session', {
    method: 'DELETE',
    body: JSON.stringify({ session_id: sessionId })
  })
  resetSessionId()
}