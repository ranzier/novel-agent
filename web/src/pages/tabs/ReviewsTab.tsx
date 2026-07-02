import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api";

// 伏笔/线索埋设超过这么多章仍未回收，视为陈旧（与后端 mid_term.STALE_AFTER 一致）。
const STALE_AFTER = 8;

// 渲染一条伏笔/线索：兼容旧的纯字符串与新的 {text, planted_chapter} 对象；陈旧标红。
function renderThread(t: any, i: number, currentChapter: number) {
  const text = typeof t === "string" ? t : t?.text ?? t?.content ?? "";
  const planted = typeof t === "object" && t ? t.planted_chapter ?? 0 : 0;
  const age = planted > 0 ? currentChapter - planted : 0;
  const stale = planted > 0 && age >= STALE_AFTER;
  return (
    <li key={i}>
      {text}
      {stale && (
        <span className="tag err" style={{ marginLeft: 6 }}>
          已埋 {age} 章
        </span>
      )}
    </li>
  );
}

export function ReviewsTab({ slug }: { slug: string }) {
  const qc = useQueryClient();
  const { data: reviews } = useQuery({
    queryKey: ["reviews", slug],
    queryFn: () => api.reviews(slug),
  });
  const { data: state } = useQuery({
    queryKey: ["state", slug],
    queryFn: () => api.state(slug),
  });
  const { data: ov } = useQuery({
    queryKey: ["overview", slug],
    queryFn: () => api.overview(slug),
  });
  const progLabel = ov?.progression_label || "状态";

  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (state && editing) setText(JSON.stringify(state, null, 2));
  }, [state, editing]);

  const startEdit = () => {
    setText(JSON.stringify(state ?? {}, null, 2));
    setMsg("");
    setEditing(true);
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
      await api.saveState(slug, parsed);
      await qc.invalidateQueries({ queryKey: ["state", slug] });
      await qc.invalidateQueries({ queryKey: ["overview", slug] });
      setMsg("已保存 ✓");
      setEditing(false);
    } catch (e: any) {
      setMsg("保存失败：" + e.message);
    }
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
      <div>
        <h2 style={{ marginTop: 0 }}>一致性校验</h2>
        {reviews?.length === 0 && <p className="muted">暂无校验记录。</p>}
        {reviews?.map((r) => {
          const issues = r.issues ?? [];
          const errs = issues.filter((i: any) => i.severity === "error");
          const warns = issues.filter((i: any) => i.severity === "warn");
          return (
            <div key={r.chapter} className="card" style={{ marginBottom: 10 }}>
              <div className="spread">
                <strong>第 {r.chapter} 章</strong>
                {issues.length === 0 ? (
                  <span className="tag ok">通过</span>
                ) : (
                  <span>
                    {errs.length > 0 && (
                      <span className="tag err">{errs.length} 硬伤</span>
                    )}{" "}
                    {warns.length > 0 && (
                      <span className="tag warn">{warns.length} 疑点</span>
                    )}
                  </span>
                )}
              </div>
              {issues.map((i: any, k: number) => (
                <div
                  key={k}
                  style={{ fontSize: 13, marginTop: 6 }}
                  className={i.severity === "error" ? "" : "muted"}
                >
                  <span
                    className={`tag ${i.severity === "error" ? "err" : "warn"}`}
                  >
                    {i.category}
                  </span>{" "}
                  {i.message}
                </div>
              ))}
            </div>
          );
        })}
      </div>

      <div>
        <div className="spread" style={{ marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>世界状态（记忆）</h2>
          <div className="row">
            {msg && <span className="muted">{msg}</span>}
            {editing ? (
              <>
                <button onClick={() => { setEditing(false); setMsg(""); }}>
                  取消
                </button>
                <button className="primary" onClick={save}>
                  保存
                </button>
              </>
            ) : (
              <button onClick={startEdit}>编辑</button>
            )}
          </div>
        </div>

        {editing ? (
          <>
            <p
              className="muted"
              style={{ marginTop: 0, marginBottom: 8, fontSize: 13 }}
            >
              直接编辑完整世界状态 JSON。这是写作时注入的“硬事实”记忆，改动会影响后续章节的连贯性，请谨慎修改。
            </p>
            <textarea
              rows={28}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setMsg("");
              }}
              style={{ fontFamily: "monospace", fontSize: 13 }}
            />
          </>
        ) : (
          <div className="card">
            <p>
              <span className="muted">时间：</span>
              {state?.timeline || "—"}
            </p>
            <p>
              <span className="muted">主角{progLabel}：</span>
              {state?.protagonist_tier || "—"}
            </p>
            <p>
              <span className="muted">主角位置：</span>
              {state?.protagonist_location || "—"}
            </p>
            <div className="muted" style={{ marginTop: 10 }}>
              进行中的冲突/任务
            </div>
            <ul>
              {(state?.open_threads ?? []).map((t: any, i: number) =>
                renderThread(t, i, state?.last_chapter ?? 0),
              )}
              {(state?.open_threads ?? []).length === 0 && (
                <li className="muted">—</li>
              )}
            </ul>
            <div className="muted" style={{ marginTop: 10 }}>
              未回收伏笔
            </div>
            <ul>
              {(state?.foreshadowing ?? []).map((f: any, i: number) =>
                renderThread(f, i, state?.last_chapter ?? 0),
              )}
              {(state?.foreshadowing ?? []).length === 0 && (
                <li className="muted">—</li>
              )}
            </ul>
            <div className="muted">角色状态</div>
            <ul>
              {(state?.characters ?? []).map((c: any, i: number) => (
                <li key={i}>
                  {c.name} · {c.power_tier || "—"}{" "}
                  {c.status === "死亡" && <span className="tag err">死亡</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
