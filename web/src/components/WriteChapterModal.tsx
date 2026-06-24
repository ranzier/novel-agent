// 写单章设置弹窗：指定本章目标字数。

import { useState } from "react";

export function WriteChapterModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void;
  onConfirm: (opts: { words: number }) => void;
}) {
  const [words, setWords] = useState(2500);

  return (
    <div className="drawer-mask" onClick={onClose}>
      <div
        className="card"
        style={{ width: 380, margin: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0 }}>写下一章</h3>

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
          <button className="primary" onClick={() => onConfirm({ words })}>
            开始写作
          </button>
        </div>
      </div>
    </div>
  );
}
