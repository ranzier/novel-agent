import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";
import { BatchModal } from "../../components/BatchModal";
import { WriteChapterModal } from "../../components/WriteChapterModal";
import { ExtendOutlineModal } from "../../components/ExtendOutlineModal";
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
  const [showExtend, setShowExtend] = useState(false);
  const [actionMsg, setActionMsg] = useState("");

  if (!ov) return <p className="muted">加载中…</p>;
  const st = ov.state ?? {};

  const startWrite = async (opts: { words: number; author_note: string }) => {
    setShowWrite(false);
    setActionMsg("");
    try {
      const { task_id } = await api.write(slug, { chapter: 0, ...opts });
      onTask(task_id, "写下一章");
    } catch (e: any) {
      setActionMsg(e.message || "写作失败，请先确认大纲已规划到下一章");
    }
  };
  const extendOutline = async (count: number) => {
    setShowExtend(false);
    setActionMsg("");
    try {
      const { task_id } = await api.extendOutline(slug, count);
      onTask(task_id, `续写大纲（${count} 章）`);
    } catch (e: any) {
      setActionMsg(e.message || "续写大纲失败");
    }
  };
  const startBatch = async (opts: {
    count: number;
    words: number;
    author_note: string;
  }) => {
    setShowBatch(false);
    setActionMsg("");
    try {
      const { task_id } = await api.run(slug, opts);
      onTask(
        task_id,
        opts.count > 0 ? `批量续写 ${opts.count} 章` : "批量续写到末尾",
      );
    } catch (e: any) {
      setActionMsg(e.message || "批量续写失败，请先确认大纲已规划到下一章");
    }
  };

  // total 为 0 表示尚未生成大纲，无法写章
  const noOutline = ov.progress.total === 0;
  // 已写章数 ≥ 已规划章数 → 大纲已写完，需续写大纲
  const allPlannedWritten =
    ov.progress.total > 0 && ov.progress.written >= ov.progress.total;

  return (
    <div className="grid" style={{ gap: 18 }}>
      <div className="spread">
        <h2 style={{ margin: 0 }}>{ov.title}</h2>
        <div className="row">
          {allPlannedWritten ? (
            <button className="primary" onClick={() => setShowExtend(true)}>
              ✚ 续写大纲
            </button>
          ) : (
            <button
              className="primary"
              onClick={() => setShowWrite(true)}
              disabled={noOutline}
            >
              ✍ 写下一章
            </button>
          )}
          <button
            onClick={() => setShowBatch(true)}
            disabled={allPlannedWritten || noOutline}
          >
            ⏩ 批量续写
          </button>
        </div>
      </div>

      {noOutline && (
        <div className="card" style={{ padding: 12, fontSize: 13 }}>
          <div style={{ marginBottom: 4 }}>还没有大纲，无法写章节。</div>
          <span className="muted">
            请先到「大纲」标签页生成大纲，再回来写下一章。
          </span>
        </div>
      )}
      {actionMsg && (
        <div
          className="card"
          style={{ padding: 12, fontSize: 13, color: "var(--red)" }}
        >
          {actionMsg}
        </div>
      )}

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
      {showExtend && (
        <ExtendOutlineModal
          onClose={() => setShowExtend(false)}
          onConfirm={extendOutline}
        />
      )}
    </div>
  );
}
