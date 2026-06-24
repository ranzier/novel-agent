// 订阅任务进度（SSE）。把事件按「步骤」分组，每步保留其下的明细与流式正文，
// 便于前端做可展开的手风琴。

import { useEffect, useRef, useState } from "react";

export interface ProgressEvent {
  kind: string; // step / info / warn / error / done / delta
  message: string;
  data: Record<string, any>;
}

// 一个步骤分组：标题 + 该步下的明细行 + 该步的流式正文
export interface StepGroup {
  title: string; // step 的标题；开篇未归入任何 step 的归到「准备」
  kind: string; // step / done / error —— 决定标题样式
  lines: ProgressEvent[]; // 该步下的 info/warn/error 明细
  streamText: string; // 该步的流式正文（仅写作步会有）
}

export function useTaskStream(taskId: string | null) {
  const [groups, setGroups] = useState<StepGroup[]>([]);
  const [finished, setFinished] = useState(false);
  const [doneData, setDoneData] = useState<Record<string, any> | null>(null);

  useEffect(() => {
    if (!taskId) return;
    setGroups([]);
    setFinished(false);
    setDoneData(null);

    const es = new EventSource(`/api/tasks/${taskId}/events`);

    const onMsg = (e: MessageEvent) => {
      try {
        const ev: ProgressEvent = JSON.parse(e.data);

        setGroups((prev) => {
          const next = [...prev];
          const cur = next[next.length - 1];

          if (ev.kind === "step") {
            // 新步骤开一个分组
            next.push({ title: ev.message, kind: "step", lines: [], streamText: "" });
            return next;
          }
          if (ev.kind === "delta") {
            // 正文增量累积到当前步骤
            if (cur) cur.streamText += ev.message;
            return next;
          }
          // info / warn / error / done：归入当前步骤的明细
          if (!cur) {
            // 还没有任何 step，先建一个「准备」分组
            next.push({ title: "准备", kind: "step", lines: [], streamText: "" });
          }
          next[next.length - 1].lines.push(ev);
          if (ev.kind === "done") {
            next[next.length - 1].kind = "done";
          }
          return next;
        });

        // done 事件只表示"某一步/某一章完成"，不代表整个任务结束
        // （批量写作每章都会 done）。记下最近一次 done 的数据，但任务是否
        // 真正结束由流关闭（es.onerror）判定，避免第一章后就误判完成。
        if (ev.kind === "done") {
          setDoneData(ev.data ?? {});
        }
      } catch {
        /* ignore malformed */
      }
    };

    ["step", "info", "warn", "error", "done", "delta"].forEach((k) =>
      es.addEventListener(k, onMsg as EventListener),
    );

    es.onerror = () => {
      setFinished(true);
      es.close();
    };

    return () => es.close();
  }, [taskId]);

  return { groups, finished, doneData };
}
