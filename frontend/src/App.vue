<script setup lang="ts">
import { nextTick, ref } from "vue";
import ChatPanel from "./components/ChatPanel.vue";
import DocumentPanel from "./components/DocumentPanel.vue";
import DocumentPreview from "./components/DocumentPreview.vue";
import HistoryPanel from "./components/HistoryPanel.vue";

const documentCount = ref<number | null>(null);
const previewId = ref<number | null>(null);
const view = ref<"chat" | "history">("chat");
const chat = ref<InstanceType<typeof ChatPanel>>();

async function openQuestion(questionId: number) {
  view.value = "chat";
  await nextTick();
  chat.value?.scrollToQuestion(questionId);
}
</script>

<template>
  <div class="layout">
    <DocumentPanel @count="documentCount = $event" @preview="previewId = $event" />
    <div class="workspace">
      <nav class="tabs" aria-label="主要功能">
        <button :aria-current="view === 'chat' ? 'page' : undefined" @click="view = 'chat'">問答</button>
        <button :aria-current="view === 'history' ? 'page' : undefined" @click="view = 'history'">問答歷史</button>
      </nav>
      <ChatPanel v-show="view === 'chat'" ref="chat" :document-count="documentCount" />
      <HistoryPanel v-if="view === 'history'" @open="openQuestion" />
    </div>
    <DocumentPreview :document-id="previewId" @close="previewId = null" />
  </div>
</template>
