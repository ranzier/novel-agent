// 长任务进度抽屉：步骤手风琴。每步可点击展开，查看该步的明细与流式正文；
// 进行中的步骤默认展开并实时滚动。

import { useEffect, useRef, useState } from "react";
import { useTaskStream } from "../useTaskStream";

export function ProgressDrawer({
  taskId,
  title,
  onClose,
  onDone,
}: {
  taskId: string;
  title: string;
  onClose: () => void;
  onDone?: (data: Record<string, any>) => void;
}) {
  const { groups, finished, doneData } = useTaskStream(taskId);

  // 用户手动展开/折叠的覆盖（key=步骤下标 → 是否展开）
  const [overrides, setOverrides] = useState<Record<number, boolean>>({});

  // 结束时回调一次（刷新数据）。ref 守卫避免重复触发。
  const firedRef = useRef(false);
  useEffect(() => {
    if (finished && doneData && onDone && !firedRef.current) {
      firedRef.current = true;
      onDone(doneData);
    }
  }, [finished, doneData, onDone]);

  // 当前正在进行的步骤下标（最后一个，且任务未结束）
  const activeIdx = finished ? -1 : groups.length - 1;

  const hasError = groups.some((g) => g.lines.some((l) => l.kind === "error"));

  const isOpen = (i: number) =>
    overrides[i] !== undefined ? overrides[i] : i === activeIdx;

  return (
    <div className="drawer-mask" onClick={finished ? onClose : undefined}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="spread" style={{ marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>{title}</h3>
          <button onClick={onClose} disabled={!finished}>
            {finished ? "关闭" : "进行中…"}
          </button>
        </div>

        <div style={{ flex: 1 }}>
          {groups.map((g, i) => (
            <StepBlock
              key={i}
              group={g}
              active={i === activeIdx}
              open={isOpen(i)}
              onToggle={() =>
                setOverrides((o) => ({ ...o, [i]: !isOpen(i) }))
              }
            />
          ))}
          {groups.length === 0 && (
            <div className="log-line muted">⏳ 正在启动…</div>
          )}
        </div>

        {finished && (
          <div className="card" style={{ marginTop: 16 }}>
            {hasError ? (
              <span className="tag err">任务出错</span>
            ) : (
              <span className="tag ok">完成</span>
            )}
            {doneData?.usage && (
              <div className="muted" style={{ marginTop: 8 }}>
                调用 {doneData.usage.calls} 次 · 约 ${doneData.usage.cost_usd}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function StepBlock({
  group,
  active,
  open,
  onToggle,
}: {
  group: import("../useTaskStream").StepGroup;
  active: boolean;
  open: boolean;
  onToggle: () => void;
}) {
  // 流式正文自动滚到底
  const streamRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (streamRef.current) {
      streamRef.current.scrollTop = streamRef.current.scrollHeight;
    }
  }, [group.streamText]);

  const hasDetail = group.lines.length > 0 || group.streamText;

  return (
    <div style={{ marginBottom: 6 }}>
      <div
        className={`log-line ${group.kind}`}
        onClick={hasDetail ? onToggle : undefined}
        style={{ cursor: hasDetail ? "pointer" : "default", userSelect: "none" }}
      >
        {hasDetail ? (open ? "▾ " : "▸ ") : "  "}
        {group.kind === "done" ? "✓ " : "› "}
        {group.title}
        {active && !group.streamText && <span className="muted"> …</span>}
      </div>

      {open && hasDetail && (
        <div style={{ paddingLeft: 18, marginTop: 4 }}>
          {group.lines.map((l, j) => (
            <div
              key={j}
              className={`log-line ${l.kind}`}
              style={{ whiteSpace: "pre-wrap" }}
            >
              {l.message}
            </div>
          ))}
          {group.streamText && (
            <div
              ref={streamRef}
              style={{
                marginTop: 6,
                padding: "10px 12px",
                background: "var(--panel-2)",
                borderRadius: 6,
                maxHeight: 280,
                overflowY: "auto",
                whiteSpace: "pre-wrap",
                fontSize: 13,
                lineHeight: 1.7,
              }}
            >
              {group.streamText}
              {active && <span className="muted">▌</span>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
