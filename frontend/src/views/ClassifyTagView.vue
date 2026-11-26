<template>
  <div class="ct-view" data-testid="classify-page">
    <section class="delivery-banner" data-testid="delivery-entry-banner">
      <div>
        <h3>分级分类交付 · 稀有组获准范围</h3>
        <p>
          K 匿名检查生成的稀有组放行单会在这里形成可发布范围版本；
          发生处置 / 重检冲突时，可在详情页辨认哪一版范围仍可发布，并下载获准范围、查阅历史回执。
        </p>
      </div>
      <RouterLink
        class="btn primary"
        data-testid="delivery-detail-entry"
        :to="latestLink"
      >
        进入放行交付详情
      </RouterLink>
    </section>
    <WorkbenchView module-key="classify_tag" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getClassifyDetail } from '@/api/group-release'
import WorkbenchView from './WorkbenchView.vue'

const route = useRoute()
const router = useRouter()

// 若已有放行单，横幅直接带到对应标签 / 版本；否则进入 CLAS-0004 详情（空态也有说明）。
const latestLink = ref('/classify_tag/4')

onMounted(async () => {
  // 兼容 /classify_tag?detail=4 或 ?id=4 形式的详情入口。
  const queryDetail = route.query.detail ?? route.query.id
  if (typeof queryDetail === 'string' && /^\d+$/.test(queryDetail)) {
    const order = typeof route.query.order === 'string' ? route.query.order : undefined
    await router.replace({
      path: `/classify_tag/${queryDetail}`,
      query: order ? { order } : {},
    })
    return
  }
  try {
    const detail = await getClassifyDetail(4)
    const order = detail?.publishable_order
    if (order?.id) {
      latestLink.value = `/classify_tag/${order.classify_tag_id ?? 4}?order=${encodeURIComponent(order.id)}`
    }
  } catch {
    // 保持默认入口
  }
})
</script>

<style scoped>
.delivery-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  background: #eef4ff;
  border: 1px solid #c7dbff;
  border-radius: 10px;
  padding: 12px 16px;
  margin: 12px 0;
}
.delivery-banner h3 {
  margin: 0 0 4px;
  font-size: 16px;
}
.delivery-banner p {
  margin: 0;
  color: #475467;
  font-size: 12.5px;
  max-width: 760px;
}
</style>
