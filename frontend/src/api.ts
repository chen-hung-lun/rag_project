export interface DocumentItem {
  id: number;
  filename: string;
  created_at: string;
  chunks: number;
}

export interface UploadResult {
  document_id: number;
  filename: string;
  chunks: number;
  duplicate: boolean;
}

export interface Source {
  id: number;
  filename: string;
  page: number | null;
  content: string;
  distance: number;
}

export interface ModelOption {
  backend: "ollama" | "claude_cli";
  model: string;
}

export function modelLabel(option: ModelOption) {
  return option.backend === "claude_cli" ? `Claude ${option.model}（雲端）` : `${option.model}（本機）`;
}

export interface ModelList {
  default: ModelOption;
  models: ModelOption[];
}

// 花費時間（毫秒），從後端收到問題開始算；沒走到那一步的是 null
export interface Timing {
  search_ms: number | null;
  first_token_ms: number | null;
  total_ms: number;
}

export type ChatEvent =
  | { type: "sources"; sources: Source[] }
  | { type: "token"; text: string }
  | { type: "done"; cited: number[]; timing: Timing; question_id: number | null }
  | { type: "error"; message: string; timing?: Timing };

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // 回應不是 JSON 時，改用下面的通用訊息
  }
  return `伺服器回應錯誤（${response.status}）`;
}

export async function listDocuments(): Promise<DocumentItem[]> {
  const response = await fetch("/api/documents");
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

export interface DocumentPreview {
  id: number;
  filename: string;
  sections: { page: number | null; text: string }[];
}

export async function getDocument(id: number): Promise<DocumentPreview> {
  const response = await fetch(`/api/documents/${id}`);
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

export async function uploadDocument(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/documents", { method: "POST", body: form });
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

export async function deleteDocument(id: number): Promise<void> {
  const response = await fetch(`/api/documents/${id}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await errorMessage(response));
}

// 資料庫裡的一筆問答紀錄
export interface QuestionRecord {
  id: number;
  question: string;
  answer: string;
  backend: ModelOption["backend"];
  model: string;
  status: "done" | "error" | "stopped";
  error: string | null;
  sources: { filename: string; page: number | null }[];
  search_ms: number | null;
  first_token_ms: number | null;
  total_ms: number;
  created_at: string;
}

export async function listQuestions(keyword: string, limit = 200): Promise<QuestionRecord[]> {
  const params = new URLSearchParams({ q: keyword, limit: String(limit) });
  const response = await fetch(`/api/questions?${params}`);
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

export async function listModels(): Promise<ModelList> {
  const response = await fetch("/api/models");
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

// EventSource 只支援 GET，提問用 POST，所以自己讀取串流
// model 是 null 時由後端使用預設模型
export async function streamChat(
  question: string,
  model: ModelOption | null,
  onEvent: (event: ChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, ...model }),
    signal,
  });
  if (!response.ok || !response.body) throw new Error(await errorMessage(response));

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    // 一次讀到的資料可能只有半個事件，沒讀完的留在 buffer
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const event of events) {
      if (event.startsWith("data: ")) onEvent(JSON.parse(event.slice(6)));
    }
  }
}
