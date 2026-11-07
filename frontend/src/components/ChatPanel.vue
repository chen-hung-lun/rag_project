<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import { listModels, modelLabel, streamChat, type ModelOption } from "../api";
import { clearHistory, formatSeconds, messages, saveHistory, type Message } from "../chatHistory";

const props = defineProps<{ documentCount: number | null }>();

const confirmingClear = ref(false);
const highlightedId = ref<number | null>(null);
const question = ref("");
const busy = ref(false);
const openSource = ref("");
const scroller = ref<HTMLElement>();
let controller: AbortController | null = null;
let nextId = Math.max(0, ...messages.value.map((message) => message.id)) + 1;

const MODEL_STORAGE_KEY = "chat-model";
const models = ref<ModelOption[]>([]);
const selectedModel = ref("");

const modelKey = (option: ModelOption) => `${option.backend}/${option.model}`;

const currentModel = computed(() => models.value.find((option) => modelKey(option) === selectedModel.value) ?? null);

// 優先用上次選的模型；不能用了就改用預設，預設也沒有就選第一個
async function loadModels() {
  try {
    const list = await listModels();
    models.value = list.models;
    let saved = "";
    try {
      saved = localStorage.getItem(MODEL_STORAGE_KEY) ?? "";
    } catch {
      // 無法讀取儲存空間時用預設模型
    }
    const keys = list.models.map(modelKey);
    selectedModel.value = [saved, modelKey(list.default), keys[0]].find((key) => key && keys.includes(key)) ?? "";
  } catch {
    // 讀不到清單時隱藏選單，由後端使用預設模型
    models.value = [];
  }
}

function rememberModel() {
  try {
    localStorage.setItem(MODEL_STORAGE_KEY, selectedModel.value);
  } catch {
    // 無法儲存時下次開啟改用預設模型
  }
}

const canSend = computed(() => !busy.value && question.value.trim().length > 0 && !!props.documentCount);

function createMessage(role: Message["role"], text = ""): Message {
  return { id: nextId++, role, text, sources: [], cited: [], error: "", stopped: false, createdAt: new Date().toISOString() };
}

function scrollToBottom() {
  nextTick(() => {
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
  });
}

// 把回答拆成文字和 [1] 引用，不用 v-html，文件內容才不會被當成 HTML 執行
function splitCitations(message: Message) {
  return message.text.split(/(\[\d+\])/).map((part) => {
    const number = part.match(/^\[(\d+)\]$/)?.[1];
    return number && message.sources.some((source) => source.id === Number(number))
      ? { type: "citation" as const, value: Number(number) }
      : { type: "text" as const, value: part };
  });
}

function citedSources(message: Message) {
  return message.sources.filter((source) => message.cited.includes(source.id));
}

function timingDetail(message: Message) {
  return message.timing?.search_ms == null
    ? "前端量到的時間（沒有完成，後端沒有回傳細項）"
    : "搜尋：找相關段落；第一個字：模型開始回答；耗時：從送出到回答完成";
}

function sourceKey(message: Message, id: number) {
  return `${message.id}-${id}`;
}

function toggleSource(message: Message, id: number) {
  const key = sourceKey(message, id);
  openSource.value = openSource.value === key ? "" : key;
}

function confirmClear() {
  clearHistory();
  confirmingClear.value = false;
}

// 問答歷史點一筆紀錄時，捲到畫面上對應的回答
function scrollToQuestion(questionId: number) {
  const answer = messages.value.find((message) => message.questionId === questionId);
  if (!answer) return;
  highlightedId.value = answer.id;
  nextTick(() => document.getElementById(`message-${answer.id}`)?.scrollIntoView({ block: "center" }));
}

defineExpose({ scrollToQuestion });

async function send() {
  if (!canSend.value) return;

  const text = question.value.trim();
  question.value = "";
  busy.value = true;
  messages.value.push(createMessage("user", text));
  messages.value.push(createMessage("assistant"));
  const answer = messages.value[messages.value.length - 1];
  const model = currentModel.value;
  if (model) answer.model = modelLabel(model);
  scrollToBottom();

  const startedAt = performance.now();
  controller = new AbortController();
  try {
    await streamChat(
      text,
      model,
      (event) => {
        if (event.type === "sources") answer.sources = event.sources;
        else if (event.type === "token") answer.text += event.text;
        else if (event.type === "done") {
          answer.cited = event.cited;
          answer.timing = event.timing;
          if (event.question_id != null) answer.questionId = event.question_id;
        } else {
          answer.error = event.message;
          answer.timing = event.timing;
        }
        scrollToBottom();
      },
      controller.signal,
    );
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") answer.stopped = true;
    else answer.error = error instanceof Error ? error.message : "發生錯誤";
  } finally {
    // 按停止或連線失敗時沒有後端的時間，改用前端量到的總時間
    answer.timing ??= { search_ms: null, first_token_ms: null, total_ms: Math.round(performance.now() - startedAt) };
    busy.value = false;
    controller = null;
    saveHistory();
    scrollToBottom();
  }
}

onMounted(() => {
  scrollToBottom();
  loadModels();
});

function onEnter(event: KeyboardEvent) {
  // 注音選字時的 Enter 是確認選字，不是送出
  if (event.isComposing || event.shiftKey) return;
  event.preventDefault();
  send();
}
</script>

<template>
  <main class="chat">
    <div v-if="models.length || messages.length" class="history-bar">
      <label v-if="models.length" class="model-picker">
        <span class="meta">回答模型</span>
        <select v-model="selectedModel" :disabled="busy" @change="rememberModel">
          <option v-for="option in models" :key="modelKey(option)" :value="modelKey(option)">
            {{ modelLabel(option) }}
          </option>
        </select>
      </label>
      <template v-if="messages.length">
        <template v-if="confirmingClear">
          <button class="text-button danger" @click="confirmClear">確定清除畫面</button>
          <button class="text-button" @click="confirmingClear = false">取消</button>
        </template>
        <button v-else class="text-button" title="只清除畫面上的對話，問答歷史仍保留在資料庫" :disabled="busy" @click="confirmingClear = true">清除畫面</button>
      </template>
    </div>
    <div ref="scroller" class="messages" aria-live="polite">
      <div v-if="!messages.length" class="welcome">
        <h2>{{ documentCount ? "想查什麼？" : "先加入文件" }}</h2>
        <p>
          {{ documentCount
            ? "用自然的句子提問，回答會標出依據的段落。"
            : "在左側上傳文件後，就可以開始提問。" }}
        </p>
      </div>

      <template v-for="message in messages" :key="message.id">
        <div v-if="message.role === 'user'" class="bubble-row">
          <p class="user-bubble">{{ message.text }}</p>
        </div>

        <article v-else :id="`message-${message.id}`" class="answer" :class="{ highlighted: highlightedId === message.id }">
          <p class="answer-text">
            <template v-for="(part, index) in splitCitations(message)" :key="index">
              <button
                v-if="part.type === 'citation'"
                class="citation"
                :aria-label="`查看來源 ${part.value}`"
                @click="toggleSource(message, part.value)"
              >{{ part.value }}</button>
              <template v-else>{{ part.value }}</template>
            </template>
            <span v-if="busy && !message.text && !message.error && message === messages[messages.length - 1]" class="thinking">
              尋找資料中…
            </span>
          </p>

          <p v-if="message.model || message.timing" class="meta">
            <template v-if="message.model">{{ message.model }}</template>
            <template v-if="message.model && message.timing"> · </template>
            <span v-if="message.timing" :title="timingDetail(message)">耗時 {{ formatSeconds(message.timing.total_ms) }}</span>
            <template v-if="message.timing?.search_ms != null">
              （搜尋 {{ formatSeconds(message.timing.search_ms) }}<template v-if="message.timing.first_token_ms != null">、第一個字 {{ formatSeconds(message.timing.first_token_ms) }}</template>）
            </template>
          </p>
          <p v-if="message.stopped" class="status">已停止</p>
          <p v-if="message.error" class="status failed">{{ message.error }}</p>

          <ul v-if="citedSources(message).length" class="sources">
            <li v-for="source in citedSources(message)" :key="source.id">
              <button
                class="source-button"
                :aria-expanded="openSource === sourceKey(message, source.id)"
                @click="toggleSource(message, source.id)"
              >
                <span class="source-number">{{ source.id }}</span>
                <span class="filename">{{ source.filename }}</span>
                <span v-if="source.page" class="meta">第 {{ source.page }} 頁</span>
              </button>
              <blockquote v-if="openSource === sourceKey(message, source.id)">{{ source.content }}</blockquote>
            </li>
          </ul>
        </article>
      </template>
    </div>

    <form class="composer" @submit.prevent="send">
      <textarea
        v-model="question"
        rows="2"
        maxlength="2000"
        aria-label="輸入問題"
        :placeholder="documentCount ? '輸入問題，Enter 送出，Shift + Enter 換行' : '請先加入文件'"
        :disabled="!documentCount"
        @keydown.enter="onEnter"
      ></textarea>
      <button v-if="busy" type="button" class="secondary-button" @click="controller?.abort()">停止</button>
      <button v-else type="submit" class="primary-button" :disabled="!canSend">送出</button>
    </form>
  </main>
</template>
