// 写单章设置弹窗：指定本章目标字数。

import { useState } from "react";

export function WriteChapterModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void;
  onConfirm: (opts: { words: number; author_note: string }) => void;
}) {
  const [words, setWords] = useState(2500);
  const [note, setNote] = useState("");

  return (
    <div className="drawer-mask" onClick={onClose}>
      <div
        className="card"
        style={{ width: 460, margin: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0 }}>写下一章</h3>

        <label className="muted">本章思路 / 要求（可选）</label>
        <textarea
          rows={4}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="写下你对这一章的想法，AI 会优先按你的思路来写。例如：这章让主角当众识破知县的贪墨证据，气氛要爽快，结尾留个新悬念。"
          style={{ margin: "6px 0 14px" }}
        />

        <label className="muted">本章目标字数</label>
        <input
          type="number"
          min={500}
          step={100}
          value={words}
          onChange={(e) => setWords(Math.max(500, +e.target.value))}
          style={{ margin: "6px 0 8px" }}
        />
        <div className="muted" style={{ fontSize: 12, marginBottom: 16 }}>
          为目标值，实际生成会有出入（模型对中文字数控制不精确）。
        </div>

        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button onClick={onClose}>取消</button>
          <button
            className="primary"
            onClick={() => onConfirm({ words, author_note: note.trim() })}
          >
            开始写作
          </button>
        </div>
      </div>
    </div>
  );
}
