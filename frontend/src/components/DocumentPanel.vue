<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { deleteDocument, listDocuments, uploadDocument, type DocumentItem } from "../api";

const emit = defineEmits<{ count: [value: number]; preview: [id: number] }>();

const documents = ref<DocumentItem[]>([]);
const loadError = ref("");
const notices = ref<{ text: string; failed: boolean }[]>([]);
const uploadingName = ref("");
const dragging = ref(false);
const confirmingId = ref<number | null>(null);
const selected = ref<number[]>([]);
const confirmingBatch = ref(false);
const deleting = ref(false);
const fileInput = ref<HTMLInputElement>();

const allSelected = computed(
  () => documents.value.length > 0 && selected.value.length === documents.value.length,
);

function toggleAll() {
  selected.value = allSelected.value ? [] : documents.value.map((document) => document.id);
  confirmingBatch.value = false;
}

async function refresh() {
  try {
    documents.value = await listDocuments();
    const ids = new Set(documents.value.map((document) => document.id));
    selected.value = selected.value.filter((id) => ids.has(id));
    loadError.value = "";
    emit("count", documents.value.length);
  } catch {
    loadError.value = "無法連線到後端，請確認 API 伺服器已啟動。";
  }
}

async function upload(files: FileList | null) {
  if (!files?.length || uploadingName.value) return;
  notices.value = [];

  for (const file of Array.from(files)) {
    uploadingName.value = file.name;
    try {
      const result = await uploadDocument(file);
      notices.value.push({
        text: result.duplicate
          ? `${file.name}：內容和「${result.filename}」相同，沒有重複加入`
          : `${file.name}：已加入，共 ${result.chunks} 段`,
        failed: false,
      });
    } catch (error) {
      notices.value.push({
        text: `${file.name}：${error instanceof Error ? error.message : "上傳失敗"}`,
        failed: true,
      });
    }
  }

  uploadingName.value = "";
  if (fileInput.value) fileInput.value.value = "";
  await refresh();
}

async function removeSelected() {
  confirmingBatch.value = false;
  deleting.value = true;
  notices.value = [];
  let failed = 0;
  // 逐筆刪除，其中一份失敗時其他文件仍會刪除
  for (const id of selected.value) {
    try {
      await deleteDocument(id);
    } catch {
      failed += 1;
    }
  }
  const total = selected.value.length;
  notices.value = [{
    text: failed ? `已刪除 ${total - failed} 份，${failed} 份失敗` : `已刪除 ${total} 份`,
    failed: failed > 0,
  }];
  deleting.value = false;
  await refresh();
}

function onDrop(event: DragEvent) {
  dragging.value = false;
  upload(event.dataTransfer?.files ?? null);
}

async function remove(id: number) {
  confirmingId.value = null;
  try {
    await deleteDocument(id);
  } catch (error) {
    notices.value = [{ text: error instanceof Error ? error.message : "刪除失敗", failed: true }];
  }
  await refresh();
}

onMounted(refresh);
</script>

<template>
  <aside class="documents">
    <h1>文件問答</h1>

    <label
      class="dropzone"
      :class="{ dragging, busy: uploadingName }"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <input
        ref="fileInput"
        type="file"
        multiple
        accept=".pdf,.docx,.txt,.md"
        :disabled="!!uploadingName"
        @change="upload(($event.target as HTMLInputElement).files)"
      />
      <template v-if="uploadingName">
        <strong>處理中…</strong>
        <span class="filename">{{ uploadingName }}</span>
      </template>
      <template v-else>
        <strong>選擇檔案或拖曳到這裡</strong>
        <span>PDF、Word、TXT、Markdown，單檔 50 MB 內</span>
      </template>
    </label>

    <ul v-if="notices.length" class="notices">
      <li v-for="notice in notices" :key="notice.text" :class="{ failed: notice.failed }">
        {{ notice.text }}
      </li>
    </ul>

    <p v-if="loadError" class="load-error">{{ loadError }}</p>

    <h2>已加入的文件 <span v-if="documents.length">{{ documents.length }}</span></h2>
    <p v-if="!documents.length && !loadError" class="empty">還沒有文件</p>
    <div v-if="documents.length" class="batch-bar">
      <label>
        <input type="checkbox" :checked="allSelected" :disabled="deleting" @change="toggleAll" />
        全選
      </label>
      <template v-if="selected.length">
        <template v-if="confirmingBatch">
          <button class="text-button danger" @click="removeSelected">確定刪除 {{ selected.length }} 份</button>
          <button class="text-button" @click="confirmingBatch = false">取消</button>
        </template>
        <button v-else class="text-button danger" :disabled="deleting" @click="confirmingBatch = true">
          {{ deleting ? "刪除中…" : `刪除選取的 ${selected.length} 份` }}
        </button>
      </template>
    </div>
    <ul class="document-list">
      <li v-for="document in documents" :key="document.id">
        <input
          v-model="selected"
          type="checkbox"
          :value="document.id"
          :disabled="deleting"
          :aria-label="`選取 ${document.filename}`"
          @change="confirmingBatch = false"
        />
        <button class="document-info" :title="`預覽 ${document.filename}`" @click="emit('preview', document.id)">
          <span class="filename">{{ document.filename }}</span>
          <span class="meta">{{ document.chunks }} 段</span>
        </button>
        <template v-if="confirmingId === document.id">
          <button class="text-button danger" @click="remove(document.id)">確定刪除</button>
          <button class="text-button" @click="confirmingId = null">取消</button>
        </template>
        <button v-else class="text-button" @click="confirmingId = document.id">刪除</button>
      </li>
    </ul>
  </aside>
</template>
