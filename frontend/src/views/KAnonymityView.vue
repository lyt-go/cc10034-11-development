<template>
  <div class="ka-view" data-testid="ka-review-page">
    <GroupDispositionPanel />
    <WorkbenchView module-key="k_anonymity" />
  </div>
</template>

<script setup lang="ts">
import GroupDispositionPanel from './GroupDispositionPanel.vue'
import WorkbenchView from './WorkbenchView.vue'
</script>
