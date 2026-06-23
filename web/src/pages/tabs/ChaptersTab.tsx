import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";
import type { RunningTask } from "../Workspace";

export function ChaptersTab({
  slug,
  onTask,
}: {
  slug: string;
  onTask: (id: string, title: string) => void;
}) {
  const { data: chapters } = useQuery({
    queryKey: ["chapters", slug],
    queryFn: () => api.chapters(slug),
  });
  const [sel, setSel] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");

  const { data: ch } = useQuery({
    queryKey: ["chapter", slug, sel],
    queryFn: () => api.chapter(slug, sel!),
    enabled: sel !== null,
  });

  useEffect(() => {
    if (ch) {
      setText(ch.text);
      setEditing(false);
      setMsg("");
    }
  }, [ch]);

  const writeNext = async () => {
    const { task_id } = await api.write(slug, { chapter: 0 });
    onTask(task_id, "写下一章");
  };
  const runBatch = async () => {
    const { task_id } = await api.run(slug, { count: 0 });
    onTask(task_id, "批量续写");
  };
  const save = async () => {
    try {
      await api.saveChapter(slug, sel!, text);
      setMsg("已保存 ✓");
      setEditing(false);
    } catch (e: any) {
      setMsg("保存失败：" + e.message);
    }
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 20 }}>
      <div>
        <div className="row" style={{ marginBottom: 12 }}>
          <button className="primary" onClick={writeNext}>
            ✍ 下一章
          </button>
          <button onClick={runBatch}>⏩ 批量</button>
        </div>
        {chapters?.map((c) => (
          <div
            key={c.index}
            className={`nav-item ${sel === c.index ? "active" : ""}`}
            onClick={() => setSel(c.index)}
          >
            <span className="muted">第{c.index}章</span> {c.title}
            {c.has_errors && (
              <span className="tag err" style={{ marginLeft: 6 }}>
                !
              </span>
            )}
          </div>
        ))}
        {chapters?.length === 0 && (
          <p className="muted">还没有章节，点「下一章」开始。</p>
        )}
      </div>

      <div>
        {sel === null && <p className="muted">从左侧选一章查看。</p>}
        {ch && (
          <>
            <div className="spread" style={{ marginBottom: 12 }}>
              <h2 style={{ margin: 0 }}>
                第 {ch.index} 章 {ch.title}
              </h2>
              <div className="row">
                {msg && <span className="muted">{msg}</span>}
                {editing ? (
                  <>
                    <button onClick={() => setEditing(false)}>取消</button>
                    <button className="primary" onClick={save}>
                      保存
                    </button>
                  </>
                ) : (
                  <button onClick={() => setEditing(true)}>编辑</button>
                )}
              </div>
            </div>
            {editing ? (
              <textarea
                rows={30}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            ) : (
              <div className="reader">{ch.text}</div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
