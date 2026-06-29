import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api";
import { ExtendOutlineModal } from "../../components/ExtendOutlineModal";
import type { RunningTask } from "../Workspace";

export function OutlineTab({
  slug,
  onTask,
}: {
  slug: string;
  onTask: (id: string, title: string) => void;
}) {
  const qc = useQueryClient();
  const { data, error } = useQuery({
    queryKey: ["outline", slug],
    queryFn: () => api.outline(slug),
    retry: false,
  });
  const [firstWindow, setFirstWindow] = useState(10);
  const [firstNote, setFirstNote] = useState("");
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");
  const [showExtend, setShowExtend] = useState(false);

  useEffect(() => {
    if (data) setText(JSON.stringify(data, null, 2));
  }, [data]);

  const gen = async () => {
    const { task_id } = await api.genOutline(slug, {
      window: firstWindow,
      author_note: firstNote.trim(),
    });
    onTask(task_id, "生成大纲");
  };

  const extendOutline = async (count: number, authorNote: string) => {
    setShowExtend(false);
    setMsg("");
    try {
      const { task_id } = await api.extendOutline(slug, count, authorNote);
      onTask(task_id, `续写大纲（${count} 章）`);
    } catch (e: any) {
      setMsg("续写大纲失败：" + e.message);
    }
  };

  const save = async () => {
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      setMsg("JSON 格式错误，请检查");
      return;
    }
    try {
      await api.saveOutline(slug, parsed);
      await qc.invalidateQueries({ queryKey: ["outline", slug] });
      setMsg("已保存 ✓");
      setEditing(false);
    } catch (e: any) {
      setMsg("保存失败：" + e.message);
    }
  };

  // 大纲未生成
  if (error) {
    return (
      <div className="card" style={{ maxWidth: 480 }}>
        <h3 style={{ marginTop: 0 }}>还没有大纲</h3>
        <div className="row" style={{ margin: "12px 0" }}>
          <label className="muted">首次生成章数</label>
          <input
            type="number"
            min={1}
            max={30}
            value={firstWindow}
            onChange={(e) =>
              setFirstWindow(Math.min(30, Math.max(1, +e.target.value)))
            }
          />
        </div>
        <label className="muted">
          你对开头这几章的剧情设想（可选）
        </label>
        <textarea
          value={firstNote}
          onChange={(e) => setFirstNote(e.target.value)}
          rows={6}
          placeholder="例如：开篇让主角魂穿后先在军屯站稳脚跟，靠现代农技解决一桩减产危机立威；前几章铺垫冯恪以章程刁难、阿筠部族遭瘴疫，高潮放在主角识破一桩屯田舞弊。"
          style={{
            width: "100%",
            margin: "6px 0 12px",
            resize: "vertical",
            fontFamily: "inherit",
            lineHeight: 1.6,
          }}
        />
        <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
          先生成全书骨架（主线与各卷弧光，卷数由 AI 按故事体量自定），
          再细化开头这 {firstWindow} 章的章节细纲。填写设想后，AI 会以你的意图为最高优先级编排这几章
          （骨架仍由设定决定，且会遵守既定设定）。后续可在大纲页「续写大纲」。
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
      <div className="spread" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>大纲</h2>
        <div className="row">
          {msg && <span className="muted">{msg}</span>}
          {editing ? (
            <>
              <button
                onClick={() => {
                  setEditing(false);
                  setMsg("");
                  if (data) setText(JSON.stringify(data, null, 2));
                }}
              >
                取消
              </button>
              <button className="primary" onClick={save}>
                保存
              </button>
            </>
          ) : (
            <>
              <button onClick={() => setShowExtend(true)}>✚ 续写大纲</button>
              <button onClick={() => setEditing(true)}>编辑大纲</button>
            </>
          )}
        </div>
      </div>
      <div
        className="muted"
        style={{
          fontSize: 12,
          padding: "8px 12px",
          background: "var(--panel-2)",
          borderRadius: 6,
          marginBottom: 16,
        }}
      >
        ℹ 卷的划分由每批次生成的章节决定（每次生成/续写大纲 = 新的一卷），
        并非按剧情弧划分，不影响正文连贯。
        {editing && "　编辑为 JSON 格式，注意保持结构正确。"}
      </div>

      {editing ? (
        <textarea
          rows={32}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setMsg("");
          }}
          style={{ fontFamily: "monospace", fontSize: 13 }}
        />
      ) : (
        <>
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
              <div
                className="muted"
                style={{ fontSize: 13, margin: "6px 0 10px" }}
              >
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
        </>
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
