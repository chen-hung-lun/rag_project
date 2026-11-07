<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { listQuestions, modelLabel, type QuestionRecord } from "../api";
import { formatSeconds, messages } from "../chatHistory";

// 問答歷史讀資料庫的 questions 表；問答頁的「清除畫面」不會影響這裡
const emit = defineEmits<{ open: [questionId: number] }>();
const query = ref("");
const records = ref<QuestionRecord[]>([]);
const loading = ref(true);
const error = ref("");
const expanded = ref<number | null>(null);
let timer: ReturnType<typeof setTimeout> | undefined;
let latestRequest = 0;

async function load() {
  const request = ++latestRequest;
  loading.value = true;
  try {
    const result = await listQuestions(query.value.trim());
    // 打字很快時，只採用最後一次搜尋的結果
    if (request !== latestRequest) return;
    records.value = result;
    error.value = "";
  } catch (reason) {
    if (request !== latestRequest) return;
    error.value = reason instanceof Error ? reason.message : "讀取問答歷史失敗";
  } finally {
    if (request === latestRequest) loading.value = false;
  }
}

// 停止打字 0.3 秒後才搜尋，不要每打一個字就呼叫一次後端
watch(query, () => {
  clearTimeout(timer);
  timer = setTimeout(load, 300);
});
onMounted(load);
onBeforeUnmount(() => clearTimeout(timer));

// 問答頁畫面上還有的回答，點了直接跳過去；已經清掉的就在這裡展開
const onScreen = computed(() => new Set(messages.value.map((message) => message.questionId)));

function select(record: QuestionRecord) {
  if (onScreen.value.has(record.id)) emit("open", record.id);
  else expanded.value = expanded.value === record.id ? null : record.id;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString("zh-TW", { dateStyle: "short", timeStyle: "short" });
}

function cleanAnswer(text: string) {
  return text.replace(/\s*\[\d+\]/g, "");
}

function sourceNames(record: QuestionRecord) {
  return [...new Set(record.sources.map((source) => source.filename))].join("、");
}

const STATUS_TEXT = { done: "", stopped: "已停止", error: "出錯" } as const;
</script>

<template>
  <section class="history-panel">
    <input v-model="query" type="search" maxlength="200" aria-label="搜尋問答歷史" placeholder="搜尋問題或回答" />
    <p v-if="error" class="status failed">{{ error }}</p>
    <p v-else class="status">{{ loading ? "讀取中…" : `共 ${records.length} 筆（存在資料庫，清除畫面不會刪除）` }}</p>
    <p v-if="!loading && !error && !records.length" class="empty">
      {{ query.trim() ? "沒有符合的紀錄" : "還沒有問答紀錄，去問第一個問題吧。" }}
    </p>
    <ul class="history-list">
      <li v-for="record in records" :key="record.id">
        <button
          class="history-item"
          :aria-expanded="onScreen.has(record.id) ? undefined : expanded === record.id"
          @click="select(record)"
        >
          <span class="history-question">Q：{{ record.question }}</span>
          <span class="history-answer" :class="{ expanded: expanded === record.id }">
            A：{{ cleanAnswer(record.answer) || record.error || "沒有回答" }}
          </span>
          <span class="meta">
            <template v-if="STATUS_TEXT[record.status]">{{ STATUS_TEXT[record.status] }} · </template>
            <template v-if="record.sources.length">來源：{{ sourceNames(record) }} · </template>
            {{ modelLabel(record) }}
            · 耗時 {{ formatSeconds(record.total_ms) }}
            · {{ formatDate(record.created_at) }}
            <template v-if="!onScreen.has(record.id)"> · {{ expanded === record.id ? "點擊收合" : "點擊展開" }}</template>
          </span>
        </button>
      </li>
    </ul>
  </section>
</template>
