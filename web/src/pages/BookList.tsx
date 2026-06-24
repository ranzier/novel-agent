import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { ProgressDrawer } from "../components/ProgressDrawer";

export function BookList() {
  const qc = useQueryClient();
  const { data: books, isLoading } = useQuery({
    queryKey: ["books"],
    queryFn: api.listBooks,
  });
  const [showNew, setShowNew] = useState(false);
  const [task, setTask] = useState<string | null>(null);

  return (
    <div className="container">
      <div className="spread" style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>📚 网文写作 Agent</h1>
        <div className="row">
          <Link to="/settings">
            <button>⚙ 配置</button>
          </Link>
          <button className="primary" onClick={() => setShowNew(true)}>
            + 新建项目
          </button>
        </div>
      </div>

      {isLoading && <p className="muted">加载中…</p>}
      {books && books.length === 0 && (
        <p className="muted">还没有项目，点右上角新建一个吧。</p>
      )}

      <div className="grid cols">
        {books?.map((b) => {
          const pct = b.progress.total
            ? Math.round((b.progress.written / b.progress.total) * 100)
            : 0;
          return (
            <Link key={b.slug} to={`/book/${b.slug}`} className="card">
              <div className="spread">
                <strong style={{ fontSize: 16 }}>{b.title}</strong>
                <span className="tag">{b.genre}</span>
              </div>
              <div className="muted" style={{ margin: "10px 0 6px" }}>
                {b.progress.written} / {b.progress.total} 章
              </div>
              <div className="progress-bar">
                <div style={{ width: `${pct}%` }} />
              </div>
            </Link>
          );
        })}
      </div>

      {showNew && (
        <NewBookModal
          onClose={() => setShowNew(false)}
          onStart={(t) => {
            setTask(t);
            setShowNew(false);
          }}
        />
      )}
      {task && (
        <ProgressDrawer
          taskId={task}
          title="立项中"
          onClose={() => setTask(null)}
          onDone={() => qc.invalidateQueries({ queryKey: ["books"] })}
        />
      )}
    </div>
  );
}

function NewBookModal({
  onClose,
  onStart,
}: {
  onClose: () => void;
  onStart: (taskId: string) => void;
}) {
  const [idea, setIdea] = useState("");
  const [genre, setGenre] = useState("玄幻");
  const [title, setTitle] = useState("");

  const submit = async () => {
    if (!idea.trim()) return;
    const { task_id } = await api.createBook({ idea, genre, title });
    onStart(task_id);
  };

  return (
    <div className="drawer-mask" onClick={onClose}>
      <div
        className="card"
        style={{ width: 480, margin: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0 }}>新建项目</h3>
        <label className="muted">一句话创意</label>
        <textarea
          rows={3}
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder="如：废柴少年觉醒吞噬天赋，靠吞噬妖兽和敌人的能力逆袭"
          style={{ margin: "6px 0 12px" }}
        />
        <div className="row" style={{ marginBottom: 16 }}>
          <input
            value={genre}
            onChange={(e) => setGenre(e.target.value)}
            placeholder="题材"
          />
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="书名（留空让 AI 起）"
          />
        </div>
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button onClick={onClose}>取消</button>
          <button className="primary" onClick={submit}>
            开始立项
          </button>
        </div>
      </div>
    </div>
  );
}
