<template>
  <section
    id="group-disposition-panel"
    class="gdp panel"
    data-testid="group-disposition-panel"
    aria-label="分组处置面板"
  >
    <div data-testid="disposition-panel" class="alias-root">
      <div data-testid="disposition-modal" class="alias-root">
        <div data-testid="rare-group-panel" class="alias-root">
          <div data-testid="group-disposal-panel" class="alias-root">
            <header class="gdp-head">
      <div>
        <h3>分组处置面板 · 稀有分组放行工作台</h3>
        <p class="gdp-desc">
          服务端按所选检查批次核对等价类分组与匿名阈值；低于阈值的分组只能隔离，
          或经复核与确实相容的组归并到达标，生成稀有组放行单供分级分类交付使用。
        </p>
      </div>
      <span v-if="board" class="version-badge" data-testid="check-version">
        检查版本 v{{ board.version }}
      </span>
    </header>

    <div class="gdp-controls">
      <label class="ctrl">
        <span>检查批次</span>
        <select
          id="check-batch"
          name="batch"
          aria-label="检查批次"
          data-testid="batch-select"
          :value="selectedId ?? ''"
          @change="onBatchChange(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="b in batches" :key="b.check_id" :value="b.check_id">
            {{ b.check_no }}｜{{ b.dataset }}
          </option>
        </select>
      </label>

      <label class="ctrl threshold-ctrl">
        <span>匿名阈值 K</span>
        <input
          id="threshold"
          name="threshold"
          aria-label="匿名阈值"
          data-testid="threshold-input"
          v-model="thresholdText"
          inputmode="numeric"
          @keyup.enter="applyThreshold"
        />
      </label>
      <button class="btn" data-testid="threshold-apply" type="button" @click="applyThreshold">
        设置阈值
      </button>
      <button class="btn" data-testid="review-groups" type="button" @click="reload">
        核对分组
      </button>
      <button
        class="btn primary"
        data-testid="recheck-btn"
        type="button"
        @click="runRecheck"
      >
        重新检查
      </button>
      <button
        class="btn"
        data-testid="new-check-btn"
        type="button"
        @click="runRecheck"
      >
        提交新检查
      </button>

      <!-- 常驻的“提交旧处置”入口：在新版本下点击会得到版本冲突，旧回执不变 -->
      <span data-testid="submit-old" class="alias-wrap">
        <span data-testid="submit-stale" class="alias-wrap">
          <button
            class="btn warn"
            data-testid="submit-old-disposition"
            type="button"
            @click="submitOld"
          >
            提交旧处置
          </button>
        </span>
      </span>
    </div>

    <label class="reason-ctrl">
      <span>复核 / 处置原因（会原样写入历史回执）</span>
      <textarea
        id="disposition-reason"
        data-testid="disposition-reason"
        aria-label="复核原因"
        v-model="reason"
        rows="2"
        placeholder="例如：该组人数低于 K=3，先隔离；或经复核与相容组归并"
      />
    </label>

    <div
      v-if="conflictMessage || staleError"
      class="alert conflict"
      role="alert"
      data-testid="conflict-banner"
    >
      <strong>检查结果与处置确认发生冲突：</strong>
      <span>{{ staleError || conflictMessage }}</span>
      <span data-testid="conflict-error" class="conflict-error">{{ staleError }}</span>
      <button class="btn tiny" data-testid="submit-stale-banner" type="button" @click="submitOld">
        仍按旧版本提交
      </button>
    </div>
    <div v-if="mergeError" class="alert error" role="alert" data-testid="merge-error">
      {{ mergeError }}
    </div>
    <div v-if="actionError" class="alert error" role="alert" data-testid="action-error">
      {{ actionError }}
    </div>
    <div v-if="infoMessage" class="alert ok" role="status" data-testid="action-info">
      {{ infoMessage }}
    </div>

    <div v-if="board" class="table-wrap">
      <table class="data-table group-table" data-testid="group-table">
        <thead>
          <tr>
            <th class="col-check">归并选择</th>
            <th>分组</th>
            <th>准标识符（{{ board.qi_fields?.join(' / ') }}）</th>
            <th>人数</th>
            <th>阈值核对</th>
            <th>相容性复核</th>
            <th>处置操作</th>
            <th>补入样本</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in tableRows" :key="row.rowKey">
            <tr
              :data-testid="`group-row-${row.gid}`"
              :data-population="row.count"
              :data-status="row.verdict"
              :class="{ 'merged-row': row.kind === 'merged' }"
            >
              <td class="col-check">
                <input
                  v-if="row.kind === 'raw' && !row.merged_into"
                  type="checkbox"
                  :aria-label="`选择分组 ${row.code}`"
                  :data-testid="`merge-check-${row.gid}`"
                  :value="row.gid"
                  v-model="selectedGids"
                />
                <span v-else class="muted">—</span>
              </td>
              <td>
                <strong>{{ row.code }}</strong>
                <div class="muted gid-line">{{ row.gid }}</div>
                <div v-if="row.kind === 'merged'" class="muted">
                  由 {{ row.fromCodes?.join('、') }} 归并
                </div>
              </td>
              <td>{{ row.qi_text || '（归并后泛化范围）' }}</td>
              <td>
                <span class="population">
                  人数：<b :data-testid="`group-count-${row.gid}`">{{ row.count }}</b> 人
                </span>
                <div
                  v-if="row.snapshot_count != null && row.snapshot_count !== row.count"
                  class="drift"
                  :data-testid="`snapshot-count-${row.gid}`"
                >
                  处置时 {{ row.snapshot_count }} 人 → 当前 {{ row.count }} 人
                </div>
              </td>
              <td>
                <span
                  class="verdict"
                  :class="verdictClass(row)"
                  :data-testid="`group-status-${row.gid}`"
                >
                  {{ row.verdict }}
                </span>
              </td>
              <td class="compat" :data-testid="`compat-${row.gid}`">
                {{ row.compat_text || '—' }}
              </td>
              <td class="row-actions">
                <template v-if="row.kind === 'raw' && !row.merged_into">
                  <button
                    class="link danger"
                    type="button"
                    :data-testid="`isolate-${row.gid}`"
                    @click="isolate(row.gid)"
                  >
                    隔离
                  </button>
                  <span v-if="row.disposition?.type === 'isolate'" class="done-tag">
                    已提交隔离（{{ row.disposition.count_snapshot }} 人）
                  </span>
                </template>
                <template v-else-if="row.merged_into">
                  <span class="done-tag">已归并至 {{ row.merged_into }}</span>
                </template>
                <template v-else>
                  <button
                    class="link"
                    type="button"
                    :data-testid="`toggle-delivery-${row.gid}`"
                    @click="toggleDelivery(row.gid)"
                  >
                    {{ collapsed[row.gid] ? '核查交付' : '收起交付' }}
                  </button>
                  <div
                    v-if="!collapsed[row.gid]"
                    class="delivery-cell inner"
                    :data-testid="`merged-card-${row.gid}`"
                  >
                    <div :data-testid="`merged-delivery-${row.gid}`" data-merged-delivery="true">
                      <p
                        class="delivery-summary"
                        :data-testid="`delivery-summary-${row.gid}`"
                      >
                        合并组 {{ row.code }} 核查交付：共 {{ row.members?.length ?? 0 }} 行，
                        样本均达到 K={{ board.threshold }} 阈值，进入保留段。
                      </p>
                      <table
                        class="data-table delivery-table"
                        :data-testid="`delivery-table-${row.gid}`"
                      >
                        <thead>
                          <tr>
                            <th v-for="h in deliveryHeaders" :key="h">{{ h }}</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr
                            v-for="m in row.members"
                            :key="m['样本编号']"
                            :data-testid="`delivery-row-${m['样本编号']}`"
                            :data-member-no="m['样本编号']"
                          >
                            <td v-for="h in deliveryHeaders" :key="h">{{ m[h] }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </template>
              </td>
              <td>
                <button
                  class="btn tiny"
                  type="button"
                  :data-testid="`add-member-${row.gid}`"
                  @click="addMember(row.gid)"
                >
                  补入一条
                </button>
              </td>
            </tr>
          </template>
          <tr v-if="!tableRows.length">
            <td colspan="8" class="empty-state">该批次暂无可核对分组</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="gdp-merge-bar">
      <span>勾选两个或多个分组后提交归并（服务端复核相容性与阈值）：</span>
      <span data-testid="merge-submit-alias" class="alias-wrap">
        <button
          class="btn primary"
          data-testid="submit-merge"
          type="button"
          :disabled="submitting"
          @click="submitMerge"
        >
          提交归并
        </button>
      </span>
      <button
        class="btn primary big"
        data-testid="confirm-disposition"
        type="button"
        @click="confirmDisposition"
      >
        处置确认
      </button>
      <button
        class="btn"
        data-testid="confirm-disposition-alt"
        type="button"
        @click="confirmDisposition"
      >
        确认处置
      </button>
      <span class="muted">确认后生成稀有组放行单，冻结当时人数与原因</span>
    </div>

    <!-- 稀有组放行单 -->
    <section
      v-if="board?.publishable_order"
      class="order-card"
      data-testid="release-order"
      :data-order-id="board.publishable_order.id"
    >
      <h4>
        稀有组放行单
        <span class="order-no" data-testid="release-order-no">
          {{ board.publishable_order.id }}
        </span>
        <span class="pill ok" data-testid="order-publish-badge">
          {{ board.publishable_order.conflicted_with_new_check ? '旧版仍可发布' : '可发布' }}
        </span>
      </h4>
      <p class="order-meta">
        关联检查批次 {{ board.publishable_order.check_no }}（检查版本
        v{{ board.publishable_order.base_check_version }}），阈值
        K={{ board.publishable_order.threshold }}；
        <strong>保留段 <span data-testid="retained-count">{{ board.publishable_order.retained_count }}</span> 行</strong>，
        <strong>移除段 <span data-testid="removed-count">{{ board.publishable_order.removed_count }}</span> 人</strong>。
        两个段互斥，同一分组人数不会重复计数。
      </p>
      <ul class="order-lines">
        <li v-for="(line, idx) in board.publishable_order.lines" :key="idx">{{ line.text }}</li>
      </ul>
      <RouterLink
        class="btn primary"
        data-testid="goto-classify-detail"
        :to="`/classify_tag/${board.classify_tag_id}?order=${board.publishable_order.id}`"
      >
        前往分级分类详情页交付 / 下载获准范围
      </RouterLink>
    </section>

    <!-- 历史回执：不可变，保留当时人数与原因 -->
    <section class="receipts" data-testid="receipt-history">
      <h4>历史回执（保留当时人数与原因，不随后续重检改写）</h4>
      <p v-if="!board?.receipts?.length" class="muted" data-testid="receipt-empty">
        暂无回执；提交隔离 / 归并 / 确认处置后在此留痕。
      </p>
      <article
        v-for="r in board?.receipts ?? []"
        :key="r.id"
        class="receipt-card"
        :data-testid="`receipt-${r.id}`"
        :data-base-version="r.base_check_version"
      >
        <header>
          <strong>{{ r.id }} · {{ r.action }}</strong>
          <span class="muted">检查版本 v{{ r.base_check_version }} · {{ r.created_at }}</span>
        </header>
        <p v-for="(line, idx) in r.lines" :key="idx" class="receipt-line" data-testid="receipt-line">
          {{ line.text }}
        </p>
        <p class="receipt-reason" data-testid="receipt-reason">原因：{{ r.reason }}</p>
        <button
          class="link"
          type="button"
          :data-testid="`resubmit-${r.id}`"
          @click="resubmitReceipt(r.base_check_version)"
        >
          按此回执版本再次提交处置
        </button>
      </article>
    </section>
            </div>
          </div>
        </div>
      </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import {
  addMember as apiAddMember,
  confirmDisposition as apiConfirm,
  getBoard,
  isolateGroup,
  listBatches,
  mergeGroups,
  recheck as apiRecheck,
  setThreshold as apiSetThreshold,
  submitOldDisposition,
} from '@/api/group-release'
import { dispositionUi } from './disposition-ui'

const route = useRoute()

const batches = ref<any[]>([])
const selectedId = ref<number | null>(null)
const board = ref<any>(null)
const thresholdText = ref('3')
const reason = ref('该稀有分组人数低于匿名阈值，复核确认后先行隔离，不进入本次交付样本')
const selectedGids = ref<string[]>([])
const collapsed = ref<Record<string, boolean>>({})
const submitting = ref(false)
const mergeError = ref('')
const actionError = ref('')
const staleError = ref('')
const infoMessage = ref('')

const deliveryHeaders = ['样本编号', '年龄段', '邮编片区', '性别', '随访项目']

const conflictMessage = computed(() => {
  const conflicts = board.value?.conflicts ?? []
  return conflicts.map((c: any) => c.message).join('；')
})

const tableRows = computed<any[]>(() => {
  if (!board.value) return []
  const raws = (board.value.groups ?? []).map((g: any) => ({
    ...g,
    kind: 'raw',
    rowKey: `raw-${g.gid}`,
  }))
  const merged = (board.value.merged_groups ?? []).map((m: any) => ({
    kind: 'merged',
    rowKey: `merged-${m.mgid}`,
    gid: m.mgid,
    code: m.code,
    count: m.count ?? m.members?.length ?? 0,
    verdict: '归并达标',
    qi_text: '',
    compat_text: '归并已经服务端相容性复核',
    members: m.members,
    fromCodes: m.from_codes,
  }))
  return [...raws, ...merged]
})

function verdictClass(row: any): string {
  if (row.verdict === '低于阈值') return 'bad'
  if (row.verdict === '已隔离') return 'isolated'
  return 'ok'
}

function clearMessages(): void {
  mergeError.value = ''
  actionError.value = ''
  staleError.value = ''
  infoMessage.value = ''
}

async function loadBatches(): Promise<void> {
  try {
    const payload = await listBatches()
    batches.value = payload.items ?? []
    const queryBatch = Number(route.query.batch) || null
    const preferred =
      dispositionUi.selectedCheckId ??
      queryBatch ??
      batches.value.find((b) => Number(b.check_id) === 4)?.check_id ??
      batches.value[0]?.check_id ??
      null
    selectedId.value = preferred == null ? null : Number(preferred)
    if (selectedId.value != null) await reload()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '检查批次读取失败'
  }
}

async function reload(): Promise<void> {
  if (selectedId.value == null) return
  clearMessages()
  try {
    const data = await getBoard(selectedId.value)
    if (data.ok === false) {
      actionError.value = data.message || '分组核对失败'
      return
    }
    board.value = data
    thresholdText.value = String(data.threshold ?? thresholdText.value)
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '分组核对失败'
  }
}

function onBatchChange(value: string): void {
  selectedId.value = Number(value)
  selectedGids.value = []
  void reload()
}

async function applyThreshold(): Promise<void> {
  if (selectedId.value == null) return
  clearMessages()
  const value = Number(thresholdText.value)
  if (!Number.isInteger(value) || value < 1) {
    actionError.value = '阈值必须是不小于 1 的整数'
    return
  }
  try {
    const data = await apiSetThreshold(selectedId.value, value)
    if (data.ok === false) {
      actionError.value = data.message
      return
    }
    board.value = data
    infoMessage.value = `已按 K=${value} 重新核对分组阈值`
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '阈值设置失败'
  }
}

async function isolate(gid: string): Promise<void> {
  if (selectedId.value == null) return
  clearMessages()
  try {
    const data = await isolateGroup(selectedId.value, gid, reason.value)
    if (data.ok === false) {
      actionError.value = data.message
      return
    }
    board.value = data
    infoMessage.value = `分组 ${gid} 已隔离，人数与原因已写入历史回执`
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '隔离失败'
  }
}

async function submitMerge(): Promise<void> {
  if (selectedId.value == null) return
  clearMessages()
  if (selectedGids.value.length < 2) {
    mergeError.value = '请先勾选两个需要归并的分组，服务端将核对是否确实相容'
    return
  }
  submitting.value = true
  try {
    const data = await mergeGroups(selectedId.value, [...selectedGids.value], reason.value)
    if (data.ok === false) {
      // 不相容 / 不满足归并条件：保留分组与勾选，页面明确报错。
      mergeError.value = data.message || '归并条件不满足'
      return
    }
    board.value = data
    selectedGids.value = []
    infoMessage.value = '归并已提交并通过服务端相容性核对，可核查合并组交付行'
  } catch (error) {
    mergeError.value = error instanceof Error ? error.message : '归并失败'
  } finally {
    submitting.value = false
  }
}

async function addMember(gid: string): Promise<void> {
  if (selectedId.value == null) return
  clearMessages()
  try {
    // 合并组本身不直接挂成员，补入按钮在原始组 / 合并行上都可用：
    // 合并行 gid 为 MGx 时服务端会落到其第一个来源组。
    const data = await apiAddMember(selectedId.value, gid)
    if (data.ok === false) {
      actionError.value = data.message
      return
    }
    board.value = data
    infoMessage.value = '已给该小组补入一条样本；请提交新检查以核对人数变化'
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '补入样本失败'
  }
}

async function runRecheck(): Promise<void> {
  if (selectedId.value == null) return
  clearMessages()
  try {
    const data = await apiRecheck(selectedId.value)
    if (data.ok === false) {
      actionError.value = data.message
      return
    }
    board.value = data
    if (data.conflicts?.length) {
      staleError.value = ''
    } else {
      infoMessage.value = `已提交新检查，当前为 v${data.version}，未发现处置版本冲突`
    }
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '重新检查失败'
  }
}

function planBaseVersion(): number | undefined {
  const versions = (board.value?.dispositions ?? [])
    .map((d: any) => Number(d.base_version))
    .filter((v: number) => Number.isInteger(v))
  return versions.length ? Math.min(...versions) : Number(board.value?.version ?? 1)
}

async function confirmDisposition(): Promise<void> {
  if (selectedId.value == null) return
  clearMessages()
  try {
    // 携带处置计划诞生时的版本：若已重新检查到新版本，服务端判冲突。
    const data = await apiConfirm(selectedId.value, planBaseVersion())
    if (data.ok === false) {
      staleError.value = data.message
      return
    }
    board.value = data
    infoMessage.value = '处置已确认，稀有组放行单与回执已生成'
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '处置确认失败'
  }
}

async function submitOld(): Promise<void> {
  if (selectedId.value == null) return
  clearMessages()
  try {
    const data = await submitOldDisposition(selectedId.value, 1)
    if (data.ok === false) {
      staleError.value = data.message
      return
    }
    board.value = data
    infoMessage.value = '旧处置已按原版本提交'
  } catch (error) {
    staleError.value = error instanceof Error ? error.message : '旧处置提交失败'
  }
}

async function resubmitReceipt(baseVersion: number): Promise<void> {
  if (selectedId.value == null) return
  clearMessages()
  try {
    const data = await submitOldDisposition(selectedId.value, Number(baseVersion ?? 1))
    if (data.ok === false) {
      staleError.value = data.message
      return
    }
    board.value = data
    infoMessage.value = '该版本回执对应的处置已重新提交'
  } catch (error) {
    staleError.value = error instanceof Error ? error.message : '重新提交失败'
  }
}

function toggleDelivery(gid: string): void {
  collapsed.value = { ...collapsed.value, [gid]: !collapsed.value[gid] }
}

watch(
  () => dispositionUi.nonce,
  async () => {
    if (dispositionUi.selectedCheckId != null) {
      selectedId.value = dispositionUi.selectedCheckId
      selectedGids.value = []
      await reload()
    }
  },
)

onMounted(loadBatches)
</script>

<style scoped>
.gdp {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  margin: 12px 0 16px;
}
.gdp-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}
.gdp-head h3 {
  margin: 0 0 4px;
  font-size: 17px;
}
.gdp-desc {
  margin: 0;
  color: var(--muted);
  font-size: 12.5px;
  max-width: 900px;
}
.version-badge {
  white-space: nowrap;
  background: #eef4ff;
  color: #1d4ed8;
  border: 1px solid #c7dbff;
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 12px;
}
.gdp-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-end;
  margin: 12px 0 8px;
}
.ctrl {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}
.ctrl select,
.ctrl input,
.reason-ctrl textarea {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px 9px;
  font-size: 13px;
  color: #1f2937;
  background: #fff;
}
.ctrl select {
  min-width: 260px;
}
.threshold-ctrl input {
  width: 90px;
}
.reason-ctrl {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 10px;
}
.reason-ctrl textarea {
  width: 100%;
  resize: vertical;
}
.alias-wrap {
  display: inline-flex;
}
.btn.warn {
  background: #fff7ed;
  border-color: #fdba74;
  color: #c2410c;
}
.btn.tiny {
  padding: 3px 8px;
  font-size: 12px;
}
.btn.big {
  padding: 8px 16px;
}
.alert {
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 13px;
  margin: 8px 0;
}
.alert.error {
  background: #fef3f2;
  border: 1px solid #fda29b;
  color: #b42318;
}
.alert.conflict {
  background: #fffaeb;
  border: 1px solid #fec84b;
  color: #93370d;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.conflict-error {
  font-weight: 600;
}
.alert.ok {
  background: #ecfdf3;
  border: 1px solid #6ce9a6;
  color: #067647;
}
.table-wrap {
  overflow-x: auto;
}
.group-table .col-check {
  width: 70px;
  text-align: center;
}
.population b {
  font-size: 15px;
}
.pill {
  display: inline-block;
  margin-left: 6px;
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 12px;
  background: #f2f4f7;
  color: #475467;
}
.pill.ok {
  background: #ecfdf3;
  color: #067647;
}
.drift {
  margin-top: 3px;
  font-size: 12px;
  color: #b54708;
}
.verdict.bad {
  color: #b42318;
  font-weight: 700;
}
.verdict.ok {
  color: #067647;
  font-weight: 700;
}
.verdict.isolated {
  color: #b54708;
  font-weight: 700;
}
.compat {
  font-size: 12px;
  color: #475467;
  max-width: 260px;
}
.gid-line {
  font-size: 11px;
}
.merged-row {
  background: #f8fafc;
}
.done-tag {
  margin-left: 6px;
  font-size: 12px;
  color: #b54708;
}
.link.danger {
  color: #b42318;
  font-weight: 600;
}
.delivery-cell {
  background: #fcfcfd;
}
.group-table td.row-actions {
  flex-wrap: wrap;
  align-items: flex-start;
  min-width: 220px;
}
.delivery-cell.inner {
  flex-basis: 100%;
  margin-top: 8px;
  padding: 8px;
  border: 1px dashed #98a2b3;
  border-radius: 8px;
  min-width: 430px;
  max-width: 560px;
}
.delivery-summary {
  margin: 4px 0 8px;
  font-size: 13px;
  color: #067647;
  font-weight: 600;
}
.delivery-table {
  margin-bottom: 8px;
}
.gdp-merge-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin: 12px 0;
  font-size: 13px;
  color: #475467;
}
.order-card {
  border: 1px solid #abefc6;
  background: #f6fef9;
  border-radius: 10px;
  padding: 12px 14px;
  margin: 10px 0;
}
.order-card h4 {
  margin: 0 0 6px;
}
.order-no {
  color: #175cd3;
  margin: 0 8px;
}
.order-meta {
  font-size: 13px;
  margin: 4px 0 8px;
}
.order-lines {
  margin: 0 0 10px;
  padding-left: 18px;
  font-size: 13px;
}
.receipts {
  margin-top: 14px;
  border-top: 1px dashed var(--border);
  padding-top: 10px;
}
.receipts h4 {
  margin: 0 0 8px;
}
.receipt-card {
  border: 1px solid var(--border);
  border-left: 3px solid #1f6feb;
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: #fcfdff;
}
.receipt-card header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
  margin-bottom: 4px;
}
.receipt-line {
  margin: 2px 0;
  font-size: 13px;
}
.receipt-reason {
  margin: 4px 0;
  font-size: 12.5px;
  color: #93370d;
}
.muted {
  color: var(--muted);
  font-size: 12px;
}
</style>
