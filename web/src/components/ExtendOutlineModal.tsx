// 续写大纲设置弹窗：指定续写多少章细纲（1~30，默认 10）。

import { useState } from "react";

export function ExtendOutlineModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void;
  onConfirm: (count: number) => void;
}) {
  const [count, setCount] = useState(10);

  const clamp = (n: number) => Math.min(30, Math.max(1, n));

  return (
    <div className="drawer-mask" onClick={onClose}>
      <div
        className="card"
        style={{ width: 380, margin: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0 }}>续写大纲</h3>

        <label className="muted">续写章数（1~30）</label>
        <input
          type="number"
          min={1}
          max={30}
          value={count}
          onChange={(e) => setCount(clamp(+e.target.value))}
          style={{ margin: "6px 0 8px" }}
        />
        <div className="muted" style={{ fontSize: 12, marginBottom: 16 }}>
          基于当前剧情进度与世界状态，生成接下来 {count} 章的细纲，
          作为新的一卷追加到大纲末尾。
        </div>

        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button onClick={onClose}>取消</button>
          <button
            className="primary"
            onClick={() => onConfirm(clamp(count))}
          >
            续写 {clamp(count)} 章
          </button>
        </div>
      </div>
    </div>
  );
}
