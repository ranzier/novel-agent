// 续写大纲设置弹窗：指定续写多少章细纲（1~30，默认 10），
// 并可填写作者对接下来这几章剧情走向的意图，作为最高优先级注入续写。

import { useState } from "react";

export function ExtendOutlineModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void;
  onConfirm: (count: number, authorNote: string) => void;
}) {
  const [count, setCount] = useState(10);
  const [note, setNote] = useState("");

  const clamp = (n: number) => Math.min(30, Math.max(1, n));

  return (
    <div className="drawer-mask" onClick={onClose}>
      <div
        className="card"
        style={{ width: 460, margin: "auto" }}
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
          style={{ margin: "6px 0 12px" }}
        />

        <label className="muted">
          你对接下来这几章的剧情设想（可选）
        </label>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={6}
          placeholder="例如：这一卷让主角靠合规增产在县里立威，引出冯恪以章程刁难；阿筠所在部族遭瘴疫，主角借机施恩打开百越缺口。留几章铺垫，高潮放在主角识破一桩屯田舞弊。"
          style={{
            width: "100%",
            margin: "6px 0 8px",
            resize: "vertical",
            fontFamily: "inherit",
            lineHeight: 1.6,
          }}
        />
        <div className="muted" style={{ fontSize: 12, marginBottom: 16 }}>
          基于当前剧情进度与世界状态生成接下来 {count} 章的细纲，作为新的一卷追加到末尾。
          填写设想后，AI 会以你的意图为最高优先级来编排这几章（仍会遵守既定设定与世界状态）。
        </div>

        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button onClick={onClose}>取消</button>
          <button
            className="primary"
            onClick={() => onConfirm(clamp(count), note.trim())}
          >
            续写 {clamp(count)} 章
          </button>
        </div>
      </div>
    </div>
  );
}
