/**
 * 带鉴权的文件下载。
 *
 * **为什么不能直接 `<a href="/api/v1/...">`**：后端只认 `Authorization: Bearer`，
 * 而浏览器点链接时不会带这个头 —— 结果是一个 401 的空白页。
 * 所以下载必须走 axios（拦截器自动加 token），拿到 blob 再由前端触发保存。
 */
import http, { type RequestConfig } from '@/api/http'

/** 从 Content-Disposition 里取文件名（后端用 RFC 5987 的 filename*）。 */
function filenameOf(disposition: string | undefined, fallback: string): string {
  if (!disposition) return fallback
  const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1])
    } catch {
      // 后端编码异常时退回到普通 filename
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition)
  return plain?.[1] ?? fallback
}

/** 触发一次浏览器保存。 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // 立刻回收：大文件下延迟释放会让内存多占一会儿
  URL.revokeObjectURL(url)
}

export interface DownloadedFile {
  blob: Blob
  filename: string
}

/** 下载并返回文件（不自动保存，调用方可以决定何时保存或先做别的处理）。 */
export async function fetchFile(url: string, fallbackName = 'download'): Promise<DownloadedFile> {
  // raw=true：响应拦截器默认只返回 data，下载要读 Content-Disposition 头
  const config: RequestConfig = { responseType: 'blob', raw: true }
  const response = await http.get(url, config)
  const disposition = response.headers?.['content-disposition'] as string | undefined
  return {
    blob: response.data as Blob,
    filename: filenameOf(disposition, fallbackName),
  }
}

/** 下载并直接保存。 */
export async function downloadFile(url: string, fallbackName = 'download'): Promise<void> {
  const { blob, filename } = await fetchFile(url, fallbackName)
  saveBlob(blob, filename)
}

/**
 * 取一个可放进 `<img src>` / `<a href>` 的临时地址。
 *
 * `<img src="/api/v1/files/1/download">` 同样不带 Authorization 头，
 * 图片附件因此显示不出来 —— 只能先取回 blob 再转本地 URL。
 * **用完记得 `URL.revokeObjectURL`**，否则 blob 一直占着内存。
 */
export async function fetchObjectUrl(url: string): Promise<string> {
  const { blob } = await fetchFile(url)
  return URL.createObjectURL(blob)
}

/**
 * 打印当前页面（用浏览器的「另存为 PDF」得到 PDF）。
 *
 * 刻意不引入前端 PDF 库：单据是**给人看**的表单 + 审批记录，
 * 浏览器打印的排版与字体反而更接近屏幕效果，也省掉一份几百 KB 的依赖。
 */
export function printPage(): void {
  window.print()
}
