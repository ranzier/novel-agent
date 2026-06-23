import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";
import type { RunningTask } from "../Workspace";

export function OutlineTab({
  slug,
  onTask,
}: {
  slug: string;
  onTask: (id: string, title: string) => void;
}) {
  const { data, error } = useQuery({
    queryKey: ["outline", slug],
    queryFn: () => api.outline(slug),
    retry: false,
  });
  const [volumes, setVolumes] = useState(5);
  const [chapters, setChapters] = useState(10);

  const gen = async () => {
    const { task_id } = await api.genOutline(slug, { volumes, chapters });
    onTask(task_id, "生成大纲");
  };

  // 大纲未生成
  if (error) {
    return (
      <div className="card" style={{ maxWidth: 420 }}>
        <h3 style={{ marginTop: 0 }}>还没有大纲</h3>
        <div className="row" style={{ margin: "12px 0" }}>
          <label className="muted">卷数</label>
          <input
            type="number"
            value={volumes}
            onChange={(e) => setVolumes(+e.target.value)}
          />
          <label className="muted">每卷章数</label>
          <input
            type="number"
            value={chapters}
            onChange={(e) => setChapters(+e.target.value)}
          />
        </div>
        <button className="primary" onClick={gen}>
          生成大纲
        </button>
      </div>
    );
  }

  if (!data) return <p className="muted">加载中…</p>;

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>大纲</h2>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="muted">核心立意</div>
        <div>{data.premise || "—"}</div>
        <div className="muted" style={{ marginTop: 10 }}>
          主线
        </div>
        <div>{data.main_plot || "—"}</div>
      </div>

      {data.volumes?.map((v: any) => (
        <div key={v.index} className="card" style={{ marginBottom: 12 }}>
          <div className="spread">
            <strong>
              第 {v.index} 卷 · {v.title}
            </strong>
            <span className="muted" style={{ fontSize: 12 }}>
              {v.start_tier} → {v.end_tier}
            </span>
          </div>
          <div className="muted" style={{ fontSize: 13, margin: "6px 0 10px" }}>
            {v.arc}
          </div>
          {v.chapters?.map((c: any) => (
            <div
              key={c.index}
              style={{
                padding: "6px 0",
                borderTop: "1px solid var(--border)",
              }}
            >
              <span className="muted">第 {c.index} 章</span> {c.title}
              {c.cool_point && (
                <span className="tag ok" style={{ marginLeft: 8 }}>
                  爽点
                </span>
              )}
              <div className="muted" style={{ fontSize: 12 }}>
                {c.summary}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
