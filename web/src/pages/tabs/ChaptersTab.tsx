import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api";
import { BatchModal } from "../../components/BatchModal";
import { WriteChapterModal } from "../../components/WriteChapterModal";
import { ExtendOutlineModal } from "../../components/ExtendOutlineModal";
import { ConfirmModal } from "../../components/ConfirmModal";
import type { RunningTask } from "../Workspace";

export function ChaptersTab({
  slug,
  onTask,
}: {
  slug: string;
  onTask: (id: string, title: string) => void;
}) {
  const qc = useQueryClient();
  const { data: chapters } = useQuery({
    queryKey: ["chapters", slug],
    queryFn: () => api.chapters(slug),
  });
  const {
    data: outline,
    isError: outlineError,
    isLoading: outlineLoading,
  } = useQuery({
    queryKey: ["outline", slug],
    queryFn: () => api.outline(slug),
    retry: false,
  });
  const [sel, setSel] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");
  const [showBatch, setShowBatch] = useState(false);
  const [showWrite, setShowWrite] = useState(false);
  const [showExtend, setShowExtend] = useState(false);
  const [resumming, setResumming] = useState(false);
  const [showResumConfirm, setShowResumConfirm] = useState(false);
  const [showRewrite, setShowRewrite] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [actionMsg, setActionMsg] = useState("");

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

  // 大纲已规划到第几章 vs 已写到第几章 → 是否还有"下一章"可写
  const plannedMax = outline
    ? Math.max(
        0,
        ...(outline.volumes ?? []).flatMap((v: any) =>
          (v.chapters ?? []).map((c: any) => c.index),
        ),
      )
    : 0;
  const writtenMax = chapters?.length
    ? Math.max(...chapters.map((c) => c.index))
    : 0;
  const allPlannedWritten = plannedMax > 0 && writtenMax >= plannedMax;
  // 大纲接口 404 表示尚未生成大纲；此时无法写章，需先去「大纲」页生成
  const noOutline = !outlineLoading && (outlineError || plannedMax === 0);

  const startWrite = async (opts: { words: number; author_note: string }) => {
    setShowWrite(false);
    setActionMsg("");
    try {
      const { task_id } = await api.write(slug, { chapter: 0, ...opts });
      onTask(task_id, "写下一章");
    } catch (e: any) {
      // 后端在无大纲 / 下一章未规划 / 全部写完时返回 4xx，提示用户先续写大纲
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
  const save = async () => {
    try {
      await api.saveChapter(slug, sel!, text);
      setMsg("已保存 ✓");
      setEditing(false);
    } catch (e: any) {
      setMsg("保存失败：" + e.message);
    }
  };
  const resummarize = async () => {
    if (sel === null) return;
    setResumming(true);
    setMsg("");
    try {
      const r = await api.resummarize(slug, sel);
      setMsg(
        "摘要已重建 ✓" + (r.outline_updated ? "，大纲摘要已同步" : ""),
      );
    } catch (e: any) {
      setMsg("重建失败：" + e.message);
    } finally {
      setResumming(false);
      setShowResumConfirm(false);
    }
  };
  const rewrite = async (opts: { words: number; author_note: string }) => {
    if (sel === null) return;
    setShowRewrite(false);
    const { task_id } = await api.rewrite(slug, sel, opts);
    onTask(task_id, `重写第 ${sel} 章`);
  };
  const doDelete = async () => {
    if (sel === null) return;
    setDeleting(true);
    try {
      await api.deleteChapter(slug, sel);
      setShowDeleteConfirm(false);
      setSel(null);
      qc.invalidateQueries({ queryKey: ["chapters", slug] });
      qc.invalidateQueries({ queryKey: ["overview", slug] });
    } catch (e: any) {
      setMsg("删除失败：" + e.message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 20 }}>
      <div>
        <div className="row" style={{ marginBottom: 12 }}>
          <button
            className="primary"
            onClick={() => setShowWrite(true)}
            disabled={allPlannedWritten || noOutline}
          >
            ✍ 下一章
          </button>
          <button
            onClick={() => setShowBatch(true)}
            disabled={allPlannedWritten || noOutline}
          >
            ⏩ 批量续写
          </button>
        </div>
        {noOutline && (
          <div
            className="card"
            style={{ marginBottom: 12, padding: 12, fontSize: 13 }}
          >
            <div style={{ marginBottom: 4 }}>还没有大纲，无法写章节。</div>
            <span className="muted">
              请先到「大纲」标签页生成大纲，再回来写下一章。
            </span>
          </div>
        )}
        {actionMsg && (
          <div
            className="card"
            style={{
              marginBottom: 12,
              padding: 12,
              fontSize: 13,
              color: "var(--red)",
            }}
          >
            {actionMsg}
          </div>
        )}
        {allPlannedWritten && (
          <div
            className="card"
            style={{ marginBottom: 12, padding: 12, fontSize: 13 }}
          >
            <div style={{ marginBottom: 8 }}>
              已写完大纲规划的全部 {plannedMax} 章。
              <span className="muted">
                {" "}
                续写大纲会基于当前剧情进度生成后续章节细纲。
              </span>
            </div>
            <button className="primary" onClick={() => setShowExtend(true)}>
              ✚ 续写大纲
            </button>
          </div>
        )}
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
            <div className="spread" style={{ marginBottom: 4 }}>
              <h2 style={{ margin: 0 }}>
                第 {ch.index} 章 {ch.title}
              </h2>
              {!editing && (
                <button
                  onClick={() => setShowResumConfirm(true)}
                  disabled={resumming}
                  title="作者手改正文后，据正文重新生成本章摘要并同步大纲"
                  style={{ fontSize: 12, padding: "3px 10px", marginLeft: "auto" }}
                >
                  {resumming ? "生成中…" : "⟳ 重建摘要"}
                </button>
              )}
              {!editing && (
                <button
                  onClick={() => setShowRewrite(true)}
                  title="重新生成本章正文（覆盖现有内容，并更新摘要与世界状态）"
                  style={{ fontSize: 12, padding: "3px 10px", marginLeft: 8 }}
                >
                  ✍ 重写最新章
                </button>
              )}
              {!editing && sel === writtenMax && (
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  title="删除本章（仅限最新一章，不可撤销）"
                  style={{
                    fontSize: 12,
                    padding: "3px 10px",
                    marginLeft: 8,
                    color: "var(--red)",
                  }}
                >
                  🗑 删除本章
                </button>
              )}
              <div className="row" style={{ marginLeft: 24 }}>
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
            <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
              共 {countWords(text)} 字
              {editing && <span>（编辑中，实时统计）</span>}
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
      {showResumConfirm && (
        <ConfirmModal
          title="重建本章摘要"
          message="将根据当前正文重新生成本章摘要，并同步更新大纲中该章的摘要。适合在你手动修改正文后使用。会消耗一次模型调用。是否继续？"
          confirmText="重建摘要"
          busy={resumming}
          busyText="生成中…"
          onConfirm={resummarize}
          onClose={() => setShowResumConfirm(false)}
        />
      )}
      {showRewrite && (
        <WriteChapterModal
          title={`重写第 ${sel} 章`}
          confirmText="开始重写"
          onClose={() => setShowRewrite(false)}
          onConfirm={rewrite}
        />
      )}
      {showDeleteConfirm && (
        <ConfirmModal
          title={`删除第 ${sel} 章`}
          message="将永久删除本章正文，以及其摘要、一致性校验记录和向量索引；世界状态会回退到上一章。仅能删除最新一章，此操作不可撤销。是否继续？"
          confirmText="删除"
          busy={deleting}
          busyText="删除中…"
          onConfirm={doDelete}
          onClose={() => setShowDeleteConfirm(false)}
        />
      )}
    </div>
  );
}

// 统计正文字数：去掉开头的「# 第 N 章 标题」行，再去掉所有空白字符后计长度。
// 中文按字符计，符合网文"字数"的直觉。
function countWords(raw: string): number {
  if (!raw) return 0;
  const body = raw.replace(/^\s*#.*\n/, "");
  return body.replace(/\s/g, "").length;
}
