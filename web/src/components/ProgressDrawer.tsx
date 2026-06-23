// 长任务进度抽屉：SSE 实时滚动日志 + 结束态。

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
  const { events, finished, doneData } = useTaskStream(taskId);

  // 结束时回调（用于刷新数据）
  if (finished && doneData && onDone) {
    // 延迟到下一 tick，避免渲染中 setState
    setTimeout(() => onDone(doneData), 0);
  }

  const hasError = events.some((e) => e.kind === "error");

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
          {events.map((e, i) => (
            <div key={i} className={`log-line ${e.kind}`}>
              {e.kind === "step" && "› "}
              {e.kind === "done" && "✓ "}
              {e.message}
            </div>
          ))}
          {!finished && (
            <div className="log-line muted">⏳ 正在处理…</div>
          )}
        </div>

        {finished && (
          <div
            className="card"
            style={{ marginTop: 16 }}
          >
            {hasError ? (
              <span className="tag err">任务出错</span>
            ) : (
              <span className="tag ok">完成</span>
            )}
            {doneData?.usage && (
              <div className="muted" style={{ marginTop: 8 }}>
                调用 {doneData.usage.calls} 次 · 约 $
                {doneData.usage.cost_usd}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
