/**
 * 受限 Markdown 渲染（M8 展示型控件）。
 *
 * **为什么不引 markdown 库**：这里只需要「说明文字」级别的一小撮语法，
 * 自己实现可以严格保证**先转义、再渲染**，不会把用户配置里的 HTML 当成
 * 可执行内容。支持的子集：
 *
 * - 段落与换行
 * - `#` / `##` / `###` 标题
 * - `-` / `*` 无序列表
 * - `**粗体**`、`*斜体*`、`` `行内代码` ``
 * - `[文字](https://example.com)`（只允许 http(s) 或站内 `/` 路径）
 *
 * 后端 `form_schema._check_display` 另外拒绝原始 HTML 标签；双保险。
 */

const ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (ch) => ESCAPES[ch] ?? ch)
}

function isSafeLink(url: string): boolean {
  return /^(https?:\/\/|\/(?!\/))/i.test(url.trim())
}

function renderInline(raw: string): string {
  let text = escapeHtml(raw)
  const tokens: string[] = []

  // 行内代码先抽出来，避免里面的 * 被当成强调语法
  text = text.replace(/`([^`]+)`/g, (_match, content: string) => {
    tokens.push(`<code>${content}</code>`)
    return `\u0000TOKEN${tokens.length - 1}\u0000`
  })

  // 链接也先抽出来：href 里的 * 不能被后面的强调语法改写
  text = text.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (_match, label: string, url: string) => {
      if (!isSafeLink(url)) return label
      tokens.push(
        `<a href="${url.trim()}" target="_blank" rel="noopener noreferrer">${label}</a>`,
      )
      return `\u0000TOKEN${tokens.length - 1}\u0000`
    },
  )

  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  text = text.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')

  return text.replace(/\u0000TOKEN(\d+)\u0000/g, (_match, index: string) => tokens[Number(index)] ?? '')
}

export function renderRichText(markdown: string): string {
  const lines = markdown.replace(/\r\n?/g, '\n').split('\n')
  const blocks: string[] = []
  let paragraph: string[] = []
  let list: string[] = []

  const flushParagraph = (): void => {
    if (!paragraph.length) return
    blocks.push(`<p>${paragraph.map(renderInline).join('<br>')}</p>`)
    paragraph = []
  }
  const flushList = (): void => {
    if (!list.length) return
    blocks.push(`<ul>${list.map((item) => `<li>${renderInline(item)}</li>`).join('')}</ul>`)
    list = []
  }

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) {
      flushParagraph()
      flushList()
      continue
    }

    const listItem = /^[-*]\s+(.+)$/.exec(trimmed)
    if (listItem) {
      flushParagraph()
      list.push(listItem[1])
      continue
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed)
    if (heading) {
      flushParagraph()
      flushList()
      const level = heading[1].length
      blocks.push(`<h${level}>${renderInline(heading[2])}</h${level}>`)
      continue
    }

    flushList()
    paragraph.push(line)
  }

  flushParagraph()
  flushList()
  return blocks.join('')
}
