import dayjs from 'dayjs'

/**
 * 后端所有时间都是 **naive UTC**（见 backend/app/core/clock.py）：
 * JSON 里形如 "2026-09-22T06:12:31.123456"，不带时区标记。
 * `new Date()` 会把它当本地时间解析，于是显示差 8 小时。
 * 这里先补上 `Z` 再交给 dayjs，转成用户本地时区展示。
 */
const NAIVE_ISO = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?$/

function toLocal(value: string): dayjs.Dayjs {
  return dayjs(NAIVE_ISO.test(value) ? `${value}Z` : value)
}

export function formatDateTime(value?: string | null, fallback = '—'): string {
  if (!value) return fallback
  const parsed = toLocal(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm') : fallback
}

export function formatDate(value?: string | null, fallback = '—'): string {
  if (!value) return fallback
  const parsed = toLocal(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD') : fallback
}

export function formatRelative(value?: string | null, fallback = '—'): string {
  if (!value) return fallback
  const parsed = toLocal(value)
  if (!parsed.isValid()) return fallback
  const diffMinutes = dayjs().diff(parsed, 'minute')
  if (diffMinutes < 1) return '刚刚'
  if (diffMinutes < 60) return `${diffMinutes} 分钟前`
  if (diffMinutes < 60 * 24) return `${Math.floor(diffMinutes / 60)} 小时前`
  if (diffMinutes < 60 * 24 * 30) return `${Math.floor(diffMinutes / 1440)} 天前`
  return parsed.format('YYYY-MM-DD')
}
