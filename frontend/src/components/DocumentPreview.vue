<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { getDocument, type DocumentPreview } from "../api";

const props = defineProps<{ documentId: number | null }>();
const emit = defineEmits<{ close: [] }>();

const dialog = ref<HTMLDialogElement>();
const preview = ref<DocumentPreview | null>(null);
const error = ref("");

watch(
  () => props.documentId,
  async (id) => {
    if (id === null) {
      dialog.value?.close();
      return;
    }
    preview.value = null;
    error.value = "";
    await nextTick();
    dialog.value?.showModal();
    try {
      preview.value = await getDocument(id);
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : "讀取失敗";
    }
  },
);
</script>

<template>
  <dialog ref="dialog" class="preview" aria-labelledby="preview-title" @close="emit('close')">
    <header>
      <h2 id="preview-title">{{ preview?.filename ?? "文件預覽" }}</h2>
      <button class="text-button" @click="dialog?.close()">關閉</button>
    </header>
    <p class="meta">這裡顯示系統讀到的文字，不是原始檔案的版面。</p>
    <div class="preview-body">
      <p v-if="error" class="status failed">{{ error }}</p>
      <p v-else-if="!preview" class="status">讀取中…</p>
      <section v-for="section in preview?.sections" v-else :key="section.page ?? 0">
        <h3 v-if="section.page">第 {{ section.page }} 頁</h3>
        <p>{{ section.text }}</p>
      </section>
    </div>
  </dialog>
</template>
