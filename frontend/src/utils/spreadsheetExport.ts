/**
 * 把 Univer 工作簿快照导出为 .xlsx。
 *
 * Univer 的 xlsx 导入/导出在 Pro 包里；这里用 SheetJS 做基础导出：
 * 值、公式、合并单元格、行高/列宽。不导出颜色、字体等样式。
 */

import * as XLSX from 'xlsx'

interface UniverCell {
  v?: unknown
  f?: string
  t?: number | string
}

interface UniverSheet {
  name?: string
  cellData?: Record<string, Record<string, UniverCell>>
  mergeData?: Array<{
    startRow: number
    startColumn: number
    endRow: number
    endColumn: number
  }>
  columnData?: Record<string, { width?: number }>
  rowData?: Record<string, { h?: number }>
}

interface UniverWorkbook {
  sheetOrder?: string[]
  sheets?: Record<string, UniverSheet>
}

function cellObject(cell: UniverCell): XLSX.CellObject | null {
  const value = cell.v
  if (value === undefined || value === null) {
    // 公式单元格没有缓存结果时，给 SheetJS 一个占位结果，保留公式本身
    return cell.f ? { t: 'n', v: 0, f: cell.f } : null
  }
  if (typeof value === 'number') return { t: 'n', v: value }
  if (typeof value === 'boolean') return { t: 'b', v: value }
  return { t: 's', v: String(value) }
}

export function exportSnapshotToXlsx(
  snapshot: Record<string, unknown>,
  filename: string,
): void {
  const data = snapshot as UniverWorkbook
  const orders = data.sheetOrder?.length
    ? data.sheetOrder
    : Object.keys(data.sheets ?? {})
  if (!orders.length) {
    throw new Error('工作簿没有可导出的工作表')
  }

  const workbook = XLSX.utils.book_new()
  for (const sheetId of orders) {
    const sheet = data.sheets?.[sheetId]
    if (!sheet) continue

    const worksheet: XLSX.WorkSheet = {}
    let maxRow = 0
    let maxCol = 0
    for (const [rowKey, columns] of Object.entries(sheet.cellData ?? {})) {
      const row = Number(rowKey)
      for (const [colKey, cell] of Object.entries(columns ?? {})) {
        const col = Number(colKey)
        if (!cell) continue
        const out = cellObject(cell)
        if (!out) continue
        if (cell.f && !out.f) out.f = cell.f
        worksheet[XLSX.utils.encode_cell({ r: row, c: col })] = out
        maxRow = Math.max(maxRow, row)
        maxCol = Math.max(maxCol, col)
      }
    }
    worksheet['!ref'] = XLSX.utils.encode_range({
      s: { r: 0, c: 0 },
      e: { r: maxRow, c: maxCol },
    })

    if (sheet.mergeData?.length) {
      worksheet['!merges'] = sheet.mergeData.map((merge) => ({
        s: { r: merge.startRow, c: merge.startColumn },
        e: { r: merge.endRow, c: merge.endColumn },
      }))
    }
    if (sheet.columnData) {
      worksheet['!cols'] = Object.values(sheet.columnData).map((value) => ({
        wpx: value?.width ?? 100,
      }))
    }
    if (sheet.rowData) {
      worksheet['!rows'] = Object.entries(sheet.rowData).map(([, value]) => ({
        hpx: value?.h ?? 24,
      }))
    }

    XLSX.utils.book_append_sheet(workbook, worksheet, sheet.name || sheetId)
  }

  XLSX.writeFile(workbook, `${filename}.xlsx`)
}
