// 删除本书确认弹窗：危险操作，要求作者输入书名二次确认。

import { useState } from "react";

export function DeleteBookModal({
  title,
  onClose,
  onConfirm,
}: {
  title: string;
  onClose: () => void;
  onConfirm: () => Promise<void>;
}) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const matched = input.trim() === title.trim();

  const doDelete = async () => {
    if (!matched) return;
    setBusy(true);
    setErr("");
    try {
      await onConfirm();
    } catch (e: any) {
      setErr("删除失败：" + e.message);
      setBusy(false);
    }
  };

  return (
    <div className="drawer-mask" onClick={busy ? undefined : onClose}>
      <div
        className="card"
        style={{ width: 460, margin: "auto", borderColor: "var(--red)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0, color: "var(--red)" }}>⚠ 删除本书</h3>

        <p style={{ lineHeight: 1.8 }}>
          即将<strong>永久删除</strong>《{title}》的全部内容，包括：
          设定圣经、角色库、大纲、所有章节正文、世界状态、摘要、向量库、
          校验报告。
          <br />
          <strong style={{ color: "var(--red)" }}>
            此操作不可恢复，无法撤销。
          </strong>
        </p>

        <label className="muted" style={{ fontSize: 13 }}>
          请输入书名 <strong>{title}</strong> 以确认删除：
        </label>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={title}
          style={{ margin: "6px 0 12px" }}
          autoFocus
        />

        {err && (
          <div className="muted" style={{ color: "var(--red)", marginBottom: 10 }}>
            {err}
          </div>
        )}

        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button onClick={onClose} disabled={busy}>
            取消
          </button>
          <button
            onClick={doDelete}
            disabled={!matched || busy}
            style={{
              background: matched ? "var(--red)" : undefined,
              borderColor: matched ? "var(--red)" : undefined,
              color: matched ? "#fff" : undefined,
            }}
          >
            {busy ? "删除中…" : "永久删除"}
          </button>
        </div>
      </div>
    </div>
  );
}
