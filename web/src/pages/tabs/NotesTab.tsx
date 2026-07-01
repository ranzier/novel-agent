import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";

// 作者笔记：纯文本自由记录，仅供作者备忘，不参与 AI 写作的任何过程。
export function NotesTab({ slug }: { slug: string }) {
  const { data } = useQuery({
    queryKey: ["notes", slug],
    queryFn: () => api.notes(slug),
  });
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (data) setText(data.text ?? "");
  }, [data]);

  const save = async () => {
    try {
      await api.saveNotes(slug, text);
      setMsg("已保存 ✓");
    } catch (e: any) {
      setMsg("保存失败：" + e.message);
    }
  };

  if (!data) return <p className="muted">加载中…</p>;

  return (
    <div>
      <div className="spread" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>作者笔记</h2>
        <div className="row">
          {msg && <span className="muted">{msg}</span>}
          <button className="primary" onClick={save}>
            保存
          </button>
        </div>
      </div>
      <p className="muted" style={{ marginTop: 0, marginBottom: 12, fontSize: 13 }}>
        随手记录剧情走向、灵感、待办、设定备忘等。仅供你自己查看，不会注入写作上下文、不影响 AI 生成。
      </p>
      <textarea
        rows={28}
        value={text}
        placeholder="在这里记录你的笔记…"
        onChange={(e) => {
          setText(e.target.value);
          setMsg("");
        }}
        style={{ fontSize: 14, lineHeight: 1.7 }}
      />
    </div>
  );
}
