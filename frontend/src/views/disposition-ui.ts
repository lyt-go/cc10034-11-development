import { reactive } from 'vue'

/** 跨组件的审核台 UI 状态：列表行的「分组处置」按钮用它通知面板切换批次。 */
export const dispositionUi = reactive<{
  selectedCheckId: number | null
  nonce: number
}>({
  selectedCheckId: null,
  nonce: 0,
})

export function openDisposition(checkId: number): void {
  dispositionUi.selectedCheckId = checkId
  dispositionUi.nonce += 1
  if (typeof document !== 'undefined') {
    document
      .getElementById('group-disposition-panel')
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}
