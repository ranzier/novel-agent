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
  progression_label?: string;
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

export interface GenreTemplate {
  key: string;
  aliases: string[];
  has_progression: boolean;
  progression_label: string;
  power_system_hint: string;
  selling_point_guide: string;
  core_conflict_guide: string;
  worldview_guide: string;
  tone_hint: string;
  archetypes: string[];
  character_guide: string;
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
  listGenres: () => req<{ genres: string[] }>("/api/genres"),
  genreTemplates: () =>
    req<{ genres: GenreTemplate[] }>("/api/genres/templates"),
  saveGenreTemplate: (key: string, body: GenreTemplate) =>
    req<{ ok: boolean; genre: GenreTemplate }>(
      `/api/genres/templates/${encodeURIComponent(key)}`,
      { method: "PUT", body: JSON.stringify(body) },
    ),
  deleteGenreTemplate: (key: string) =>
    req<{ ok: boolean }>(
      `/api/genres/templates/${encodeURIComponent(key)}`,
      { method: "DELETE" },
    ),
  resetGenres: () =>
    req<{ ok: boolean; genres: GenreTemplate[] }>("/api/genres/reset", {
      method: "POST",
    }),
  overview: (slug: string) => req<Overview>(`/api/books/${slug}`),
  deleteBook: (slug: string) =>
    req<{ ok: boolean }>(`/api/books/${slug}`, { method: "DELETE" }),
  bible: (slug: string) => req<any>(`/api/books/${slug}/bible`),
  characters: (slug: string) => req<any>(`/api/books/${slug}/characters`),
  style: (slug: string) => req<any>(`/api/books/${slug}/style`),
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
  saveStyle: (slug: string, body: any) =>
    req(`/api/books/${slug}/style`, {
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
  resummarize: (slug: string, n: number) =>
    req<{ ok: boolean; summary: string; outline_updated: boolean }>(
      `/api/books/${slug}/chapters/${n}/resummarize`,
      { method: "POST" },
    ),

  // 长任务
  createBook: (body: { idea: string; genre?: string; title?: string }) =>
    req<TaskRef>("/api/books", { method: "POST", body: JSON.stringify(body) }),
  genOutline: (slug: string, body: any) =>
    req<TaskRef>(`/api/books/${slug}/outline`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  extendOutline: (slug: string, count: number, authorNote = "") =>
    req<TaskRef>(`/api/books/${slug}/extend-outline`, {
      method: "POST",
      body: JSON.stringify({ count, author_note: authorNote }),
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
  rewrite: (slug: string, chapter: number, body: any) =>
    req<TaskRef>(`/api/books/${slug}/rewrite/${chapter}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  reindex: (slug: string, rebuild = false) =>
    req<TaskRef>(`/api/books/${slug}/reindex?rebuild=${rebuild}`, {
      method: "POST",
    }),

  // 配置管理
  getConfig: () => req<Record<string, any>>("/api/config"),
  saveConfig: (body: Record<string, string>) =>
    req<{ ok: boolean; config: Record<string, any> }>("/api/config", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  testConfig: () =>
    req<{ ok: boolean; reply?: string; error?: string; usage?: any }>(
      "/api/config/test",
      { method: "POST" },
    ),
};
