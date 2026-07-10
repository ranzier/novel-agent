import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api";

// 写作风格为自由结构 JSON，用结构化 JSON 编辑器（带校验）读写。
export function StyleTab({ slug }: { slug: string }) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["style", slug],
    queryFn: () => api.style(slug),
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
      await api.saveStyle(slug, parsed);
      await qc.invalidateQueries({ queryKey: ["style", slug] });
      setMsg("已保存 ✓");
    } catch (e: any) {
      setMsg("保存失败：" + e.message);
    }
  };

  if (!data) return <p className="muted">加载中…</p>;

  return (
    <div>
      <div className="spread" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>写作风格</h2>
        <div className="row">
          {msg && <span className="muted">{msg}</span>}
          <button className="primary" onClick={save}>
            保存
          </button>
        </div>
      </div>
      <p className="muted" style={{ marginTop: 0, marginBottom: 12, fontSize: 13 }}>
        这里的约束与建议会在写下一章、批量续写时注入写作上下文。字段可自由增删。
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
    </div>
  );
}
