import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";

export function CharactersTab({ slug }: { slug: string }) {
  const { data } = useQuery({
    queryKey: ["characters", slug],
    queryFn: () => api.characters(slug),
  });
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
                {c.tier && `境界 ${c.tier}`}
              </div>
              <div>{c.personality || c.background || ""}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
