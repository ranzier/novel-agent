import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type GenreTemplate } from "../api";
import { ConfirmModal } from "../components/ConfirmModal";

// 空白模板：新建题材时的初值。
const EMPTY: GenreTemplate = {
  key: "",
  aliases: [],
  has_progression: true,
  progression_label: "",
  power_system_hint: "",
  selling_point_guide: "",
  core_conflict_guide: "",
  worldview_guide: "",
  tone_hint: "",
  archetypes: [],
  character_guide: "",
};

// 多值字段（别名/角色原型）以换行或逗号分隔编辑，含全角逗号。
function parseList(s: string): string[] {
  return s
    .split(/[\n,，]+/)
    .map((t) => t.trim())
    .filter(Boolean);
}

// 长文本引导字段的展示元信息。
const GUIDE_FIELDS: { key: keyof GenreTemplate; label: string; hint?: string }[] =
  [
    {
      key: "power_system_hint",
      label: "进阶体系指导",
      hint: "对 power_system 的指导：层级风格、命名、规则。无进阶体系的题材可说明留空。",
    },
    { key: "selling_point_guide", label: "卖点 / 爽点结构" },
    { key: "core_conflict_guide", label: "核心矛盾母题" },
    { key: "worldview_guide", label: "世界观侧重" },
    { key: "character_guide", label: "角色塑造侧重" },
  ];

export function GenreTemplates() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["genreTemplates"],
    queryFn: api.genreTemplates,
  });
  const genres = data?.genres ?? [];

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [form, setForm] = useState<GenreTemplate | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [msg, setMsg] = useState("");
  const [saving, setSaving] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [showReset, setShowReset] = useState(false);
  const [resetting, setResetting] = useState(false);

  // 首次加载默认选中第一个题材。
  useEffect(() => {
    if (selectedKey === null && !isNew && genres.length > 0) {
      setSelectedKey(genres[0].key);
    }
  }, [genres, selectedKey, isNew]);

  // 选中项变化时把对应模板拷进 form。
  useEffect(() => {
    if (isNew) return;
    if (selectedKey === null) {
      setForm(null);
      return;
    }
    const g = genres.find((x) => x.key === selectedKey);
    if (g) {
      setForm({ ...g });
      setMsg("");
    }
  }, [selectedKey, genres, isNew]);

  const select = (key: string) => {
    setIsNew(false);
    setSelectedKey(key);
  };

  const startNew = () => {
    setIsNew(true);
    setSelectedKey(null);
    setForm({ ...EMPTY });
    setMsg("");
  };

  const patch = (p: Partial<GenreTemplate>) => {
    setForm((f) => (f ? { ...f, ...p } : f));
    setMsg("");
  };

  const save = async () => {
    if (!form) return;
    const key = form.key.trim();
    if (!key) {
      setMsg("题材名（key）不能为空");
      return;
    }
    if (isNew && genres.some((g) => g.key === key)) {
      setMsg(`题材「${key}」已存在`);
      return;
    }
    setSaving(true);
    try {
      await api.saveGenreTemplate(key, { ...form, key });
      setMsg("已保存 ✓");
      setIsNew(false);
      setSelectedKey(key);
      // 刷新管理列表 + 新建项弹窗的题材下拉。
      qc.invalidateQueries({ queryKey: ["genreTemplates"] });
      qc.invalidateQueries({ queryKey: ["genres"] });
    } catch (e: any) {
      setMsg("保存失败：" + e.message);
    } finally {
      setSaving(false);
    }
  };

  const doDelete = async () => {
    if (selectedKey === null) return;
    try {
      await api.deleteGenreTemplate(selectedKey);
      setShowDelete(false);
      setSelectedKey(null);
      setForm(null);
      qc.invalidateQueries({ queryKey: ["genreTemplates"] });
      qc.invalidateQueries({ queryKey: ["genres"] });
    } catch (e: any) {
      setMsg("删除失败：" + e.message);
      setShowDelete(false);
    }
  };

  const doReset = async () => {
    setResetting(true);
    try {
      await api.resetGenres();
      setShowReset(false);
      setIsNew(false);
      setSelectedKey(null);
      qc.invalidateQueries({ queryKey: ["genreTemplates"] });
      qc.invalidateQueries({ queryKey: ["genres"] });
    } catch (e: any) {
      setMsg("恢复失败：" + e.message);
      setShowReset(false);
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="container">
      <div className="spread" style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>🏷 题材模板</h1>
        <div className="row">
          <button onClick={() => setShowReset(true)}>恢复默认</button>
          <Link to="/" className="muted">
            ← 返回项目
          </Link>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 20 }}>
        <div>
          <button
            className="primary"
            onClick={startNew}
            style={{ width: "100%", marginBottom: 12 }}
          >
            + 新建题材
          </button>
          {genres.map((g) => (
            <div
              key={g.key}
              className={`nav-item ${
                !isNew && selectedKey === g.key ? "active" : ""
              }`}
              onClick={() => select(g.key)}
            >
              {g.key}
              {!g.has_progression && (
                <span className="muted" style={{ fontSize: 11, marginLeft: 6 }}>
                  无进阶
                </span>
              )}
            </div>
          ))}
          {isNew && (
            <div className="nav-item active">
              {form?.key.trim() || "（新题材）"}
            </div>
          )}
        </div>

        <div>
          {!form && <p className="muted">从左侧选一个题材查看，或新建一个。</p>}
          {form && (
            <div className="card">
              <div style={{ marginBottom: 16 }}>
                <label className="muted" style={{ fontSize: 13 }}>
                  题材名（key，唯一标识）
                </label>
                <input
                  value={form.key}
                  disabled={!isNew}
                  placeholder="如：玄幻"
                  onChange={(e) => patch({ key: e.target.value })}
                  style={{ marginTop: 6 }}
                />
                {!isNew && (
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                    题材名不可改；重命名请新建后删除旧题材。
                  </div>
                )}
              </div>

              <div style={{ marginBottom: 16 }}>
                <label className="muted" style={{ fontSize: 13 }}>
                  别名 / 近义题材（换行或逗号分隔）
                </label>
                <textarea
                  rows={2}
                  value={form.aliases.join("\n")}
                  placeholder="修真&#10;仙侠&#10;武侠"
                  onChange={(e) => patch({ aliases: parseList(e.target.value) })}
                  style={{ marginTop: 6 }}
                />
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  立项时输入这些别名会命中本题材。
                </div>
              </div>

              <div style={{ marginBottom: 16 }}>
                <label className="row" style={{ fontSize: 13, gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={form.has_progression}
                    onChange={(e) =>
                      patch({ has_progression: e.target.checked })
                    }
                    style={{ width: "auto" }}
                  />
                  <span>有可量化进阶维度（如境界/等级/官阶）</span>
                </label>
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  关闭则为悬疑/言情类无进阶题材，角色不强制 power_tier。
                </div>
              </div>

              <div style={{ marginBottom: 16 }}>
                <label className="muted" style={{ fontSize: 13 }}>
                  进阶维度称谓
                </label>
                <input
                  value={form.progression_label}
                  placeholder="境界 / 官阶 / 等级 / 地位…（无则留空）"
                  onChange={(e) => patch({ progression_label: e.target.value })}
                  style={{ marginTop: 6 }}
                />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label className="muted" style={{ fontSize: 13 }}>
                  基调 / 文风
                </label>
                <input
                  value={form.tone_hint}
                  placeholder="如：热血爽快、节奏明快"
                  onChange={(e) => patch({ tone_hint: e.target.value })}
                  style={{ marginTop: 6 }}
                />
              </div>

              {GUIDE_FIELDS.map((f) => (
                <div key={f.key} style={{ marginBottom: 16 }}>
                  <label className="muted" style={{ fontSize: 13 }}>
                    {f.label}
                  </label>
                  <textarea
                    rows={3}
                    value={(form[f.key] as string) ?? ""}
                    onChange={(e) => patch({ [f.key]: e.target.value } as any)}
                    style={{ marginTop: 6 }}
                  />
                  {f.hint && (
                    <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                      {f.hint}
                    </div>
                  )}
                </div>
              ))}

              <div style={{ marginBottom: 16 }}>
                <label className="muted" style={{ fontSize: 13 }}>
                  典型角色原型（换行或逗号分隔）
                </label>
                <textarea
                  rows={3}
                  value={form.archetypes.join("\n")}
                  placeholder="废柴逆袭主角&#10;红颜&#10;打压主角的天才反派"
                  onChange={(e) =>
                    patch({ archetypes: parseList(e.target.value) })
                  }
                  style={{ marginTop: 6 }}
                />
              </div>

              <div className="row" style={{ justifyContent: "flex-end" }}>
                {msg && <span className="muted">{msg}</span>}
                {!isNew && (
                  <button onClick={() => setShowDelete(true)}>删除</button>
                )}
                <button className="primary" onClick={save} disabled={saving}>
                  {saving ? "保存中…" : "保存"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {showDelete && (
        <ConfirmModal
          title="删除题材"
          message={`确定删除题材「${selectedKey}」？此操作不可撤销（可用「恢复默认」找回内置题材）。`}
          confirmText="删除"
          onConfirm={doDelete}
          onClose={() => setShowDelete(false)}
        />
      )}
      {showReset && (
        <ConfirmModal
          title="恢复默认题材"
          message="将用内置的 7 个默认题材覆盖当前全部题材，你的自定义与修改都会丢失。是否继续？"
          confirmText="恢复默认"
          busy={resetting}
          busyText="恢复中…"
          onConfirm={doReset}
          onClose={() => setShowReset(false)}
        />
      )}
    </div>
  );
}
