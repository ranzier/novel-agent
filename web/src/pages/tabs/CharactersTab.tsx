import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";

export function CharactersTab({ slug }: { slug: string }) {
  const { data } = useQuery({
    queryKey: ["characters", slug],
    queryFn: () => api.characters(slug),
  });
  const { data: ov } = useQuery({
    queryKey: ["overview", slug],
    queryFn: () => api.overview(slug),
  });
  const progLabel = ov?.progression_label || "";
  const [edit, setEdit] = useState(false);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (data) setText(JSON.stringify(data, null, 2));
  }, [data]);

  const save = async () => {
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      setMsg("JSON 格式错误");
      return;
    }
    try {
      await api.saveCharacters(slug, parsed);
      setMsg("已保存 ✓");
      setEdit(false);
    } catch (e: any) {
      setMsg("保存失败：" + e.message);
    }
  };

  if (!data) return <p className="muted">加载中…</p>;
  const chars = data.characters ?? [];

  return (
    <div>
      <div className="spread" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>角色库（{chars.length}）</h2>
        <div className="row">
          {msg && <span className="muted">{msg}</span>}
          {edit ? (
            <>
              <button onClick={() => setEdit(false)}>取消</button>
              <button className="primary" onClick={save}>
                保存
              </button>
            </>
          ) : (
            <button onClick={() => setEdit(true)}>编辑</button>
          )}
        </div>
      </div>

      {!edit && (
        <div
          className="muted"
          style={{
            fontSize: 12,
            padding: "8px 12px",
            background: "var(--panel-2)",
            borderRadius: 6,
            marginBottom: 16,
            lineHeight: 1.6,
          }}
        >
          ℹ 反复出场的角色会被自动收录进角色库，但系统不会自动删除任何角色。
          建议在必要时手动删除不再重要的非核心角色（点「编辑」删掉对应条目后保存），
          以免角色库越积越大、稀释写作时注入的角色信息。
        </div>
      )}

      {edit ? (
        <textarea
          rows={28}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setMsg("");
          }}
          style={{ fontFamily: "monospace", fontSize: 13 }}
        />
      ) : (
        <div className="grid cols">
          {chars.map((c: any, i: number) => (
            <div key={i} className="card">
              <div className="spread">
                <strong>{c.name}</strong>
                <span className="tag">{c.role}</span>
              </div>
              <div className="muted" style={{ fontSize: 12, margin: "6px 0" }}>
                {c.power_tier && progLabel && `${progLabel} ${c.power_tier}`}
                {c.power_tier && !progLabel && c.power_tier}
                {c.power_tier && c.faction && " · "}
                {c.faction}
              </div>
              {Array.isArray(c.personality) && c.personality.length > 0 && (
                <div style={{ marginBottom: 4 }}>
                  {c.personality.map((p: string, k: number) => (
                    <span key={k} className="tag" style={{ marginRight: 4 }}>
                      {p}
                    </span>
                  ))}
                </div>
              )}
              <div className="muted" style={{ fontSize: 13 }}>
                {c.goal || c.background || ""}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
