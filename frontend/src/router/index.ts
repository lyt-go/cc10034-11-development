import { createRouter, createWebHistory } from 'vue-router'

import ClassifyDetailView from '@/views/ClassifyDetailView.vue'
import ClassifyTagView from '@/views/ClassifyTagView.vue'
import KAnonymityView from '@/views/KAnonymityView.vue'
import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    { path: '/k_anonymity', name: 'k-anonymity', component: KAnonymityView },
    // 审核页 / 分组处置台的语义化别名
    { path: '/k_anonymity/review', name: 'k-anonymity-review', component: KAnonymityView },
    { path: '/k_anonymity/disposition', name: 'k-anonymity-disposition', component: KAnonymityView },
    { path: '/classify_tag', name: 'classify-tag', component: ClassifyTagView },
    {
      path: '/classify_tag/:id(\\d+)',
      name: 'classify-detail',
      component: ClassifyDetailView,
      props: true,
    },
    {
      path: '/classify_tag/detail/:id(\\d+)',
      name: 'classify-detail-alt',
      component: ClassifyDetailView,
      props: true,
    },
    {
      path: '/classify_tag/detail',
      name: 'classify-detail-default',
      component: ClassifyDetailView,
    },
    {
      path: '/classify_tag/:id(\\d+)/detail',
      name: 'classify-detail-suffix',
      component: ClassifyDetailView,
      props: true,
    },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
