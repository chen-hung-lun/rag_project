import { ref } from "vue";
import type { Source, Timing } from "./api";

export interface Message {
  id: number;
  role: "user" | "assistant";
  text: string;
  sources: Source[];
  cited: number[];
  error: string;
  stopped: boolean;
  createdAt?: string;
  // 回答用的模型名稱，舊紀錄沒有這個欄位
  model?: string;
  // 花費時間；後端有回傳就用後端的，按停止時改用前端自己量的總時間
  timing?: Timing;
  // 對應資料庫 questions 表的編號，問答歷史用它找回畫面上的回答
  questionId?: number;
}

export function formatSeconds(ms: number | null | undefined) {
  return ms == null ? "" : `${(ms / 1000).toFixed(1)} 秒`;
}

const STORAGE_KEY = "chat-history";
const MAX_SAVED_MESSAGES = 200;

// 這裡存的是問答頁畫面上的對話，只存在這個瀏覽器；問答歷史分頁讀的是資料庫。
// 無痕模式或停用儲存時，頁面仍要能正常使用
function loadHistory(): Message[] {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

export const messages = ref<Message[]>(loadHistory());

export function saveHistory() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.value.slice(-MAX_SAVED_MESSAGES)));
  } catch {
    // 無法儲存時只是不保留紀錄
  }
}

export function clearHistory() {
  messages.value = [];
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // 無法存取儲存空間時，畫面上的紀錄已清除
  }
}
