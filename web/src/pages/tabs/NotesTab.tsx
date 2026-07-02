import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type NoteItem } from "../../api";

// 作者笔记：可创建多份，纯文本内容，仅供作者备忘，不参与 AI 写作的任何过程。
export function NotesTab({ slug }: { slug: string }) {
  const { data } = useQuery({
    queryKey: ["notes", slug],
    queryFn: () => api.notes(slug),
  });
  const [notes, setNotes] = useState<NoteItem[]>([]);
  const [selId, setSelId] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const dirty = useRef(false);

  useEffect(() => {
    if (data) {
      setNotes(data.notes ?? []);
      setSelId((prev) => prev ?? data.notes?.[0]?.id ?? null);
    }
  }, [data]);

  const sel = notes.find((n) => n.id === selId) ?? null;

  const persist = async (next: NoteItem[]) => {
    setNotes(next);
    try {
      await api.saveNotes(slug, next);
      setMsg("已保存 ✓");
      dirty.current = false;
    } catch (e: any) {
      setMsg("保存失败：" + e.message);
    }
  };

  const genId = () =>
    `n${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

  const addNote = async () => {
    const note: NoteItem = {
      id: genId(),
      title: "新笔记",
      content: "",
      updated_at: new Date().toISOString(),
    };
    const next = [note, ...notes];
    setSelId(note.id);
    await persist(next);
  };

  const deleteNote = async (id: string) => {
    if (!window.confirm("确定删除这份笔记？此操作不可撤销。")) return;
    const next = notes.filter((n) => n.id !== id);
    if (selId === id) setSelId(next[0]?.id ?? null);
    await persist(next);
  };

  const updateSel = (patch: Partial<NoteItem>) => {
    if (!sel) return;
    dirty.current = true;
    setMsg("");
    setNotes((ns) =>
      ns.map((n) =>
        n.id === sel.id
          ? { ...n, ...patch, updated_at: new Date().toISOString() }
          : n,
      ),
    );
  };

  const saveCurrent = async () => {
    // notes state 已是最新，直接整体保存
    await persist(notes);
  };

  if (!data) return <p className="muted">加载中…</p>;

  return (
    <div>
      <div className="spread" style={{ marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>作者笔记（{notes.length}）</h2>
        <div className="row">
          {msg && <span className="muted">{msg}</span>}
          <button className="primary" onClick={saveCurrent}>
            保存
          </button>
        </div>
      </div>
      <p className="muted" style={{ marginTop: 0, marginBottom: 12, fontSize: 13 }}>
        可创建多份笔记，随手记录剧情走向、灵感、待办、设定备忘等。仅供你自己查看，不会注入写作上下文、不影响 AI 生成。
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 16 }}>
        <div>
          <button
            onClick={addNote}
            style={{ width: "100%", marginBottom: 8 }}
          >
            ＋ 新建笔记
          </button>
          {notes.length === 0 && (
            <p className="muted" style={{ fontSize: 13 }}>
              还没有笔记，点上方新建。
            </p>
          )}
          {notes.map((n) => (
            <div
              key={n.id}
              className={`nav-item ${selId === n.id ? "active" : ""}`}
              onClick={() => setSelId(n.id)}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 6,
              }}
            >
              <span
                style={{
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {n.title || "（无标题）"}
              </span>
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  deleteNote(n.id);
                }}
                title="删除这份笔记"
                style={{ color: "var(--red)", cursor: "pointer", fontSize: 12 }}
              >
                🗑
              </span>
            </div>
          ))}
        </div>

        <div>
          {sel ? (
            <>
              <input
                type="text"
                value={sel.title}
                placeholder="笔记标题"
                onChange={(e) => updateSel({ title: e.target.value })}
                onBlur={() => dirty.current && saveCurrent()}
                style={{ marginBottom: 8, fontSize: 15 }}
              />
              <textarea
                rows={26}
                value={sel.content}
                placeholder="在这里记录你的笔记…"
                onChange={(e) => updateSel({ content: e.target.value })}
                onBlur={() => dirty.current && saveCurrent()}
                style={{ fontSize: 14, lineHeight: 1.7 }}
              />
            </>
          ) : (
            <p className="muted">从左侧选一份笔记，或点「新建笔记」。</p>
          )}
        </div>
      </div>
    </div>
  );
}
