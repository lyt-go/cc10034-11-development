<template>
  <section class="cdp page" data-testid="classify-detail-page" :data-tag-id="tagId">
    <div data-testid="classify-detail" class="alias-root">
      <div data-testid="detail-modal" class="alias-root">
        <header class="page-head">
          <div>
            <h2>分级分类详情 · 交付范围核对</h2>
            <p class="page-desc">
              展示稀有组放行单的可发布版本、获准范围下载与不可改写的历史回执；
              处置确认与重新检查冲突时，这里标明哪一版范围仍可发布。
            </p>
          </div>
          <RouterLink class="btn" data-testid="back-to-classify" to="/classify_tag">
            返回分级分类列表
          </RouterLink>
        </header>

        <div v-if="detail?.tag" class="tag-meta" data-testid="tag-meta">
          <span><b>标签编号：</b>{{ detail.tag['标签编号'] }}</span>
          <span><b>数据资源：</b>{{ detail.tag['数据资源'] }}</span>
          <span><b>安全等级：</b>{{ detail.tag['安全等级'] }}</span>
          <span><b>合规要求：</b>{{ detail.tag['合规要求'] }}</span>
        </div>

        <p v-if="loadError" class="alert error" data-testid="detail-error">{{ loadError }}</p>

        <!-- 版本列表：明确哪一版可发布、哪一版冲突不可发布 -->
        <section class="versions" data-testid="scope-versions">
          <h3>范围版本</h3>
          <p v-if="!detail?.versions?.length" class="muted" data-testid="version-empty">
            暂无放行单版本，请先在 K 匿名检查页完成分组处置。
          </p>
          <ul>
            <li
              v-for="v in detail?.versions ?? []"
              :key="v.id"
              class="version-item"
              :data-testid="`version-${v.id}`"
              :data-publishable="v.publishable ? 'true' : 'false'"
              :class="v.publishable ? 'can-publish' : 'cannot-publish'"
            >
              <span class="version-label">{{ v.label }}</span>
              <span
                class="version-badge"
                :data-testid="`version-badge-${v.id}`"
                :data-publishable="v.publishable ? 'true' : 'false'"
              >
                {{ v.state_text }}
              </span>
              <span v-if="v.retained_count != null" class="muted">
                保留 {{ v.retained_count }} 行 / 移除 {{ v.removed_count }} 人
              </span>
              <span v-if="v.message" class="version-msg">{{ v.message }}</span>
              <button
                v-if="v.publishable && v.id !== orderId"
                class="link"
                type="button"
                :data-testid="`pick-version-${v.id}`"
                @click="pickVersion(v.id)"
              >
                查看此版获准范围
              </button>
            </li>
          </ul>
        </section>

        <!-- 获准范围 + 实际下载 -->
        <section
          v-if="scopeOrder"
          class="approved"
          data-testid="approved-scope"
          :data-order-id="scopeOrder.id"
          data-publishable="true"
        >
          <h3>
            获准范围
            <span class="order-no" data-testid="approved-order-no">{{ scopeOrder.id }}</span>
            <span class="pill ok" data-testid="publishable-version" data-publishable="true">
              {{ publishBadgeText }}
            </span>
          </h3>
          <p class="scope-meta">
            依据检查批次 {{ scopeOrder.check_no }}（检查版本
            v{{ scopeOrder.base_check_version }}，K={{ scopeOrder.threshold }}）冻结；
            <strong>保留段 <span data-testid="scope-retained-count">{{ scopeOrder.retained_count }}</span> 行</strong>，
            <strong>移除段 <span data-testid="scope-removed-count">{{ scopeOrder.removed_count }}</span> 人</strong>。
            交付样本不含低于阈值的分组，保留段与移除段按组互斥、不重复计数。
          </p>

          <span data-testid="scope-download" class="alias-wrap">
            <span data-testid="approved-scope-download" class="alias-wrap">
              <span data-testid="download-csv" class="alias-wrap">
                <span data-testid="download-button" class="alias-wrap">
                  <button
                    class="btn primary"
                    type="button"
                    data-testid="download-approved-scope"
                    :data-download-url="downloadUrl"
                    @click="download"
                  >
                    <span data-testid="download-scope">下载获准范围并核对（CSV）</span>
                  </button>
                </span>
              </span>
            </span>
          </span>
          <a
            class="native-download-link"
            data-testid="download-native-link"
            :href="downloadUrl"
            download="approved-scope.csv"
          >
            下载链接（CSV）
          </a>

          <table class="data-table approved-table" data-testid="approved-table">
            <thead>
              <tr>
                <th v-for="h in headers" :key="h">{{ h }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in scopeOrder.rows"
                :key="row['样本编号']"
                :data-testid="`approved-row-${row['样本编号']}`"
                :data-member-no="row['样本编号']"
              >
                <td v-for="h in headers" :key="h">{{ row[h] }}</td>
              </tr>
            </tbody>
          </table>
          <p class="muted" data-testid="approved-row-count">
            获准交付共 {{ scopeOrder.rows?.length ?? 0 }} 行
          </p>
        </section>

        <section v-else class="approved empty-scope" data-testid="approved-scope-empty">
          <h3>获准范围</h3>
          <p>当前还没有可发布的获准范围。请回到 K 匿名检查页隔离稀有组或完成相容归并并生成放行单。</p>
          <RouterLink class="btn primary" to="/k_anonymity">前往分组处置面板</RouterLink>
        </section>

        <!-- 历史回执 -->
        <section class="receipts" data-testid="receipt-history">
          <h3>历史回执</h3>
          <p v-if="!detail?.receipts?.length" class="muted" data-testid="receipt-history-empty">
            暂无历史回执。
          </p>
          <article
            v-for="r in detail?.receipts ?? []"
            :key="r.id"
            class="receipt-card"
            :data-testid="`history-receipt-${r.id}`"
            :data-base-version="r.base_check_version"
          >
            <header>
              <strong>{{ r.id }} · {{ r.action }}</strong>
              <span class="muted">检查版本 v{{ r.base_check_version }} · {{ r.created_at }}</span>
            </header>
            <p
              v-for="(line, idx) in r.lines"
              :key="idx"
              class="receipt-line"
              data-testid="history-receipt-line"
            >
              {{ line.text }}
            </p>
            <p class="receipt-reason" data-testid="history-receipt-reason">
              当时原因：{{ r.reason }}
            </p>
          </article>
        </section>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  approvedScopeUrl,
  downloadApprovedScope,
  getClassifyDetail,
} from '@/api/group-release'

const props = defineProps<{ id?: string | number }>()

const route = useRoute()
const router = useRouter()

const tagId = computed<string | number>(() => props.id ?? String(route.params.id ?? '4'))
const orderId = ref<string | undefined>(
  typeof route.query.order === 'string' ? route.query.order : undefined,
)
const detail = ref<any>(null)
const loadError = ref('')

const headers = ['样本编号', '年龄段', '邮编片区', '性别', '随访项目']

const scopeOrder = computed<any>(() => detail.value?.publishable_order ?? null)
const downloadUrl = computed(() => approvedScopeUrl(tagId.value, orderId.value))
const publishBadgeText = computed(() => {
  const hasConflict = (detail.value?.conflicts ?? []).length > 0
  return hasConflict ? '旧版仍可发布' : '本版可发布'
})

async function load(): Promise<void> {
  loadError.value = ''
  try {
    const data = await getClassifyDetail(tagId.value, orderId.value)
    if (data?.ok === false) {
      loadError.value = data.message || '详情读取失败'
      return
    }
    detail.value = data
    if (!orderId.value && data?.publishable_order?.id) {
      orderId.value = data.publishable_order.id
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '详情读取失败'
  }
}

function download(): void {
  if (!scopeOrder.value?.id) return
  downloadApprovedScope(tagId.value, orderId.value ?? scopeOrder.value.id)
}

async function pickVersion(id: string): Promise<void> {
  orderId.value = id
  await router.replace({ query: { ...route.query, order: id } })
  await load()
}

watch(
  () => route.query.order,
  (value) => {
    if (typeof value === 'string' && value !== orderId.value) {
      orderId.value = value
      void load()
    }
  },
)

onMounted(load)
</script>

<style scoped>
.tag-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  margin-bottom: 12px;
}
.alert.error {
  background: #fef3f2;
  border: 1px solid #fda29b;
  color: #b42318;
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 13px;
}
.versions,
.approved,
.receipts {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 16px;
  margin-bottom: 14px;
}
.versions h3,
.approved h3,
.receipts h3 {
  margin: 0 0 10px;
  font-size: 16px;
}
.versions ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
.version-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 8px;
  font-size: 13px;
}
.version-item.can-publish {
  border-left: 3px solid #12b76a;
  background: #f6fef9;
}
.version-item.cannot-publish {
  border-left: 3px solid #f04438;
  background: #fffbfa;
}
.version-badge {
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 12px;
  background: #f2f4f7;
  color: #475467;
}
.version-badge[data-publishable='true'] {
  background: #d1fadf;
  color: #067647;
}
.version-badge[data-publishable='false'] {
  background: #fee4e2;
  color: #b42318;
}
.version-msg {
  flex-basis: 100%;
  color: #b54708;
  font-size: 12.5px;
}
.order-no {
  color: #175cd3;
  margin: 0 8px;
}
.pill {
  display: inline-block;
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 12px;
  background: #ecfdf3;
  color: #067647;
}
.scope-meta {
  font-size: 13px;
  color: #475467;
  margin: 4px 0 12px;
}
.alias-wrap {
  display: inline-flex;
}
.native-download-link {
  margin-left: 12px;
  font-size: 13px;
  color: var(--brand);
}
.approved-table {
  margin-top: 12px;
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
