import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";
import { BatchModal } from "../../components/BatchModal";
import { WriteChapterModal } from "../../components/WriteChapterModal";
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
  const [showBatch, setShowBatch] = useState(false);
  const [showWrite, setShowWrite] = useState(false);

  if (!ov) return <p className="muted">加载中…</p>;
  const st = ov.state ?? {};

  const startWrite = async (opts: { words: number; author_note: string }) => {
    setShowWrite(false);
    const { task_id } = await api.write(slug, { chapter: 0, ...opts });
    onTask(task_id, "写下一章");
  };
  const extendOutline = async () => {
    const { task_id } = await api.extendOutline(slug, 10);
    onTask(task_id, "续写大纲（10 章）");
  };
  const startBatch = async (opts: {
    count: number;
    words: number;
    author_note: string;
  }) => {
    setShowBatch(false);
    const { task_id } = await api.run(slug, opts);
    onTask(
      task_id,
      opts.count > 0 ? `批量续写 ${opts.count} 章` : "批量续写到末尾",
    );
  };

  // 已写章数 ≥ 已规划章数 → 大纲已写完，需续写大纲
  const allPlannedWritten =
    ov.progress.total > 0 && ov.progress.written >= ov.progress.total;

  return (
    <div className="grid" style={{ gap: 18 }}>
      <div className="spread">
        <h2 style={{ margin: 0 }}>{ov.title}</h2>
        <div className="row">
          {allPlannedWritten ? (
            <button className="primary" onClick={extendOutline}>
              ✚ 续写大纲（+10 章）
            </button>
          ) : (
            <button className="primary" onClick={() => setShowWrite(true)}>
              ✍ 写下一章
            </button>
          )}
          <button onClick={() => setShowBatch(true)} disabled={allPlannedWritten}>
            ⏩ 批量续写
          </button>
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
        {(ov.progression_label || st.protagonist_tier) && (
          <p>
            <span className="muted">
              主角{ov.progression_label || "状态"}：
            </span>
            {st.protagonist_tier || "—"}
          </p>
        )}
        {st.protagonist_location && (
          <p>
            <span className="muted">主角位置：</span>
            {st.protagonist_location}
          </p>
        )}
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

      {showBatch && (
        <BatchModal onClose={() => setShowBatch(false)} onConfirm={startBatch} />
      )}
      {showWrite && (
        <WriteChapterModal
          onClose={() => setShowWrite(false)}
          onConfirm={startWrite}
        />
      )}
    </div>
  );
}
