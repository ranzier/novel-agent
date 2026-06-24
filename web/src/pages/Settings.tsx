import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

// 配置项的展示元信息
const FIELDS: {
  key: string;
  label: string;
  sensitive: boolean;
  placeholder?: string;
  hint?: string;
}[] = [
  {
    key: "ANTHROPIC_API_KEY",
    label: "Anthropic API Key（必填）",
    sensitive: true,
    placeholder: "sk-ant-... 或网关 key",
  },
  {
    key: "ANTHROPIC_BASE_URL",
    label: "Anthropic Base URL（可选）",
    sensitive: false,
    placeholder: "走代理/兼容网关时填，如 http://llmapi.xxx",
  },
  {
    key: "NOVEL_MODEL",
    label: "写作模型（可选）",
    sensitive: false,
    placeholder: "留空用默认",
  },
  {
    key: "DASHSCOPE_API_KEY",
    label: "DashScope Key（向量召回，可选）",
    sensitive: true,
    placeholder: "通义 embedding key，不填则跳过向量召回",
  },
  {
    key: "EMBED_BASE_URL",
    label: "Embedding Base URL（可选）",
    sensitive: false,
  },
  { key: "EMBED_MODEL", label: "Embedding 模型（可选）", sensitive: false },
  { key: "EMBED_DIM", label: "Embedding 维度（可选）", sensitive: false },
];

export function Settings() {
  const { data: cfg } = useQuery({
    queryKey: ["config"],
    queryFn: api.getConfig,
  });
  const [vals, setVals] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [show, setShow] = useState<Record<string, boolean>>({});
  const [msg, setMsg] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string>("");

  // 初始化：敏感字段显示脱敏值（占位），非敏感字段显示真实值
  useEffect(() => {
    if (!cfg) return;
    const init: Record<string, string> = {};
    FIELDS.forEach((f) => {
      init[f.key] = cfg[f.key]?.value ?? "";
    });
    setVals(init);
    setTouched({});
  }, [cfg]);

  const onChange = (key: string, v: string) => {
    setVals((s) => ({ ...s, [key]: v }));
    setTouched((t) => ({ ...t, [key]: true }));
    setMsg("");
  };

  const save = async () => {
    // 只提交用户改动过的字段；敏感字段未改动则不提交（后端保留原值）
    const payload: Record<string, string> = {};
    FIELDS.forEach((f) => {
      if (touched[f.key]) payload[f.key] = vals[f.key] ?? "";
    });
    if (Object.keys(payload).length === 0) {
      setMsg("没有改动");
      return;
    }
    try {
      await api.saveConfig(payload);
      setMsg("已保存 ✓（即时生效，无需重启）");
      setTouched({});
    } catch (e: any) {
      setMsg("保存失败：" + e.message);
    }
  };

  const test = async () => {
    setTesting(true);
    setTestResult("");
    try {
      const r = await api.testConfig();
      setTestResult(
        r.ok ? `✓ 连通正常：${r.reply}` : `✗ 失败：${r.error}`,
      );
    } catch (e: any) {
      setTestResult("✗ 失败：" + e.message);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="container" style={{ maxWidth: 680 }}>
      <div className="spread" style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>⚙ 配置管理</h1>
        <Link to="/" className="muted">
          ← 返回项目
        </Link>
      </div>

      <div className="card">
        {FIELDS.map((f) => {
          const meta = cfg?.[f.key];
          const isSecret = f.sensitive && !show[f.key];
          const defaultHint = cfg?._defaults?.[f.key];
          return (
            <div key={f.key} style={{ marginBottom: 16 }}>
              <label className="muted" style={{ fontSize: 13 }}>
                {f.label}
                {meta?.is_set && f.sensitive && (
                  <span className="tag ok" style={{ marginLeft: 8 }}>
                    已设置
                  </span>
                )}
              </label>
              <div className="row" style={{ marginTop: 6 }}>
                <input
                  type={isSecret ? "password" : "text"}
                  value={vals[f.key] ?? ""}
                  placeholder={
                    f.placeholder ||
                    (defaultHint ? `默认：${defaultHint}` : "")
                  }
                  onChange={(e) => onChange(f.key, e.target.value)}
                />
                {f.sensitive && (
                  <button
                    type="button"
                    onClick={() =>
                      setShow((s) => ({ ...s, [f.key]: !s[f.key] }))
                    }
                    style={{ whiteSpace: "nowrap" }}
                  >
                    {show[f.key] ? "隐藏" : "显示"}
                  </button>
                )}
              </div>
              {f.hint && (
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  {f.hint}
                </div>
              )}
            </div>
          );
        })}

        <div className="muted" style={{ fontSize: 12, marginBottom: 14 }}>
          敏感字段（key）显示为脱敏值；不修改则保留原值。配置写入项目根目录
          .env，保存后即时生效。
        </div>

        <div className="row" style={{ justifyContent: "space-between" }}>
          <button onClick={test} disabled={testing}>
            {testing ? "测试中…" : "测试 Claude 连通"}
          </button>
          <div className="row">
            {msg && <span className="muted">{msg}</span>}
            <button className="primary" onClick={save}>
              保存
            </button>
          </div>
        </div>
        {testResult && (
          <div
            className="muted"
            style={{ marginTop: 12, fontSize: 13 }}
          >
            {testResult}
          </div>
        )}
      </div>
    </div>
  );
}
