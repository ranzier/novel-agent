// 批量续写设置弹窗：选择续写章数（0 = 写到大纲末尾）+ 每章字数。

import { useState } from "react";

export function BatchModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void;
  onConfirm: (opts: { count: number; words: number }) => void;
}) {
  const [count, setCount] = useState(3);
  const [toEnd, setToEnd] = useState(false);
  const [words, setWords] = useState(2500);

  return (
    <div className="drawer-mask" onClick={onClose}>
      <div
        className="card"
        style={{ width: 420, margin: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0 }}>批量续写</h3>

        <label className="muted">续写章数</label>
        <div className="row" style={{ margin: "6px 0 14px" }}>
          <input
            type="number"
            min={1}
            value={count}
            disabled={toEnd}
            onChange={(e) => setCount(Math.max(1, +e.target.value))}
            style={{ width: 100, opacity: toEnd ? 0.5 : 1 }}
          />
          <label className="row" style={{ gap: 6, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={toEnd}
              onChange={(e) => setToEnd(e.target.checked)}
              style={{ width: "auto" }}
            />
            <span>一直写到大纲末尾</span>
          </label>
        </div>

        <label className="muted">每章目标字数</label>
        <input
          type="number"
          min={500}
          step={100}
          value={words}
          onChange={(e) => setWords(Math.max(500, +e.target.value))}
          style={{ margin: "6px 0 16px" }}
        />

        <div className="muted" style={{ fontSize: 12, marginBottom: 14 }}>
          每章都会走完整闭环（召回 → 写 → 校验 → 固化 → 索引），
          逐章顺序生成，可在进度面板实时查看。
        </div>

        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button onClick={onClose}>取消</button>
          <button
            className="primary"
            onClick={() => onConfirm({ count: toEnd ? 0 : count, words })}
          >
            {toEnd ? "开始（写到末尾）" : `开始续写 ${count} 章`}
          </button>
        </div>
      </div>
    </div>
  );
}
