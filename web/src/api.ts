// 与后端 API 的类型与请求封装。

export interface BookSummary {
  slug: string;
  title: string;
  genre: string;
  progress: { written: number; total: number };
}

export interface Overview {
  slug: string;
  title: string;
  genre: string;
  tone: string;
  golden_finger: string;
  core_conflict: string;
  progress: { written: number; total: number };
  state: any;
}

export interface ChapterMeta {
  index: number;
  title: string;
  chars: number;
  has_errors: boolean;
}

export interface TaskRef {
  task_id: string;
  chapter?: number;
}

async function req<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  listBooks: () => req<BookSummary[]>("/api/books"),
  overview: (slug: string) => req<Overview>(`/api/books/${slug}`),
  bible: (slug: string) => req<any>(`/api/books/${slug}/bible`),
  characters: (slug: string) => req<any>(`/api/books/${slug}/characters`),
  outline: (slug: string) => req<any>(`/api/books/${slug}/outline`),
  chapters: (slug: string) => req<ChapterMeta[]>(`/api/books/${slug}/chapters`),
  chapter: (slug: string, n: number) =>
    req<{ index: number; title: string; text: string }>(
      `/api/books/${slug}/chapters/${n}`,
    ),
  state: (slug: string) => req<any>(`/api/books/${slug}/state`),
  reviews: (slug: string) => req<any[]>(`/api/books/${slug}/reviews`),

  // 编辑保存
  saveBible: (slug: string, body: any) =>
    req(`/api/books/${slug}/bible`, { method: "PUT", body: JSON.stringify(body) }),
  saveCharacters: (slug: string, body: any) =>
    req(`/api/books/${slug}/characters`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  saveOutline: (slug: string, body: any) =>
    req(`/api/books/${slug}/outline`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  saveChapter: (slug: string, n: number, text: string) =>
    req(`/api/books/${slug}/chapters/${n}`, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),

  // 长任务
  createBook: (body: { idea: string; genre?: string; title?: string }) =>
    req<TaskRef>("/api/books", { method: "POST", body: JSON.stringify(body) }),
  genOutline: (slug: string, body: any) =>
    req<TaskRef>(`/api/books/${slug}/outline`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  write: (slug: string, body: any) =>
    req<TaskRef>(`/api/books/${slug}/write`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  run: (slug: string, body: any) =>
    req<TaskRef>(`/api/books/${slug}/run`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  reindex: (slug: string, rebuild = false) =>
    req<TaskRef>(`/api/books/${slug}/reindex?rebuild=${rebuild}`, {
      method: "POST",
    }),
};
