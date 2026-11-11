/**
 * 生成请求幂等键（`X-Request-Id`），RFC 4122 v4 UUID。
 *
 * 为什么不直接 `crypto.randomUUID()`：它**只在安全上下文可用**（HTTPS、
 * localhost、127.0.0.1）。用 `http://192.168.x.x:8080` 这类局域网地址访问时，
 * 浏览器会把 `crypto.randomUUID` 置为 undefined。若在 axios 请求拦截器里直接调用，
 * 会在**请求发出之前**抛 TypeError —— DevTools 里看不到任何网络请求，axios 又把它
 * 当成「无响应的网络错误」，最终提示「无法连接服务器，请确认后端已启动」。
 *
 * 所以：能用 randomUUID 就用；否则用 `crypto.getRandomValues` 拼一个 v4；
 * 极端环境（连 Web Crypto 都没有）退化成 Math.random —— 幂等键只用于去重，
 * 不承担安全职责，可用性优先。
 */
export function newRequestId(): string {
  const c = typeof globalThis.crypto !== 'undefined' ? globalThis.crypto : undefined

  if (c && typeof c.randomUUID === 'function') {
    return c.randomUUID()
  }

  const bytes = new Uint8Array(16)
  if (c && typeof c.getRandomValues === 'function') {
    c.getRandomValues(bytes)
  } else {
    for (let i = 0; i < bytes.length; i += 1) {
      bytes[i] = Math.floor(Math.random() * 256)
    }
  }

  // version 4（0100xxxx）与 variant 10xx，保证格式与 randomUUID 一致
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80

  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join('-')
}
