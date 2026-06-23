import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";

// 设定圣经结构较深，用结构化 JSON 编辑器（带校验）最稳妥。
export function BibleTab({ slug }: { slug: string }) {
  const { data } = useQuery({
    queryKey: ["bible", slug],
    queryFn: () => api.bible(slug),
  });
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
      setMsg("JSON 格式错误，请检查");
      return;
    }
    try {
      await api.saveBible(slug, parsed);
      setMsg("已保存 ✓");
    } catch (e: any) {
      setMsg("保存失败：" + e.message);
    }
  };

  if (!data) return <p className="muted">加载中…</p>;

  return (
    <div>
      <div className="spread" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>设定圣经</h2>
        <div className="row">
          {msg && <span className="muted">{msg}</span>}
          <button className="primary" onClick={save}>
            保存
          </button>
        </div>
      </div>
      <textarea
        rows={28}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setMsg("");
        }}
        style={{ fontFamily: "monospace", fontSize: 13 }}
      />
    </div>
  );
}
