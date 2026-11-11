/**
 * 幂等键生成。
 *
 * 回归点：`crypto.randomUUID()` 只在安全上下文可用。用 http + 局域网 IP 访问时
 * 它是 undefined，原实现在 axios 请求拦截器里直接抛错 —— 请求没发出、DevTools
 * 无记录，却提示「无法连接服务器」。这里覆盖三个分支。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { newRequestId } from '@/utils/requestId'

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('newRequestId', () => {
  it('正常环境返回 v4 UUID', () => {
    expect(newRequestId()).toMatch(UUID_V4)
  })

  it('非安全上下文（没有 randomUUID）时用 getRandomValues 兜底', () => {
    let seed = 0
    vi.stubGlobal('crypto', {
      getRandomValues: (bytes: Uint8Array) => {
        for (let i = 0; i < bytes.length; i += 1) {
          bytes[i] = (seed = (seed * 31 + 17) % 256)
        }
        return bytes
      },
    })

    expect(newRequestId()).toMatch(UUID_V4)
  })

  it('连 Web Crypto 都没有也不抛错', () => {
    vi.stubGlobal('crypto', undefined)

    expect(newRequestId()).toMatch(UUID_V4)
  })

  it('每次调用都不同', () => {
    const ids = new Set(Array.from({ length: 50 }, () => newRequestId()))
    expect(ids.size).toBe(50)
  })
})
