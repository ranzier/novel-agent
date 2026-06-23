import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";
import type { RunningTask } from "../Workspace";

export function OverviewTab({
  slug,
  onTask,
}: {
  slug: string;
  onTask: (id: string, title: string) => void;
}) {
  const { data: ov } = useQuery({
    queryKey: ["overview", slug],
    queryFn: () => api.overview(slug),
  });

  if (!ov) return <p className="muted">加载中…</p>;
  const st = ov.state ?? {};

  const writeNext = async () => {
    const { task_id } = await api.write(slug, { chapter: 0 });
    onTask(task_id, "写下一章");
  };
  const runBatch = async () => {
    const { task_id } = await api.run(slug, { count: 0 });
    onTask(task_id, "批量续写到结尾");
  };

  return (
    <div className="grid" style={{ gap: 18 }}>
      <div className="spread">
        <h2 style={{ margin: 0 }}>{ov.title}</h2>
        <div className="row">
          <button className="primary" onClick={writeNext}>
            ✍ 写下一章
          </button>
          <button onClick={runBatch}>⏩ 批量续写</button>
        </div>
      </div>

      <div className="card">
        <div className="muted">金手指</div>
        <div>{ov.golden_finger || "—"}</div>
        <div className="muted" style={{ marginTop: 12 }}>
          核心矛盾
        </div>
        <div>{ov.core_conflict || "—"}</div>
        <div className="muted" style={{ marginTop: 12 }}>
          基调
        </div>
        <div>{ov.tone || "—"}</div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>世界状态快照</h3>
        <p>
          <span className="muted">主角境界：</span>
          {st.protagonist_tier || "—"}
        </p>
        <p>
          <span className="muted">未回收伏笔：</span>
          {(st.foreshadowing ?? []).length} 条
        </p>
        <p>
          <span className="muted">已故角色：</span>
          {(st.characters ?? [])
            .filter((c: any) => c.status === "死亡")
            .map((c: any) => c.name)
            .join("、") || "无"}
        </p>
      </div>
    </div>
  );
}
