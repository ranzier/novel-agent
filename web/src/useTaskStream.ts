// 订阅任务进度（SSE）。返回事件列表、是否结束、结果数据。

import { useEffect, useRef, useState } from "react";

export interface ProgressEvent {
  kind: string; // step / info / warn / error / done
  message: string;
  data: Record<string, any>;
}

export function useTaskStream(taskId: string | null) {
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [finished, setFinished] = useState(false);
  const [doneData, setDoneData] = useState<Record<string, any> | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!taskId) return;
    setEvents([]);
    setFinished(false);
    setDoneData(null);

    const es = new EventSource(`/api/tasks/${taskId}/events`);
    esRef.current = es;

    const onMsg = (e: MessageEvent) => {
      try {
        const ev: ProgressEvent = JSON.parse(e.data);
        setEvents((prev) => [...prev, ev]);
        if (ev.kind === "done") {
          setDoneData(ev.data ?? {});
          setFinished(true);
          es.close();
        }
        if (ev.kind === "error") {
          setFinished(true);
          es.close();
        }
      } catch {
        /* ignore malformed */
      }
    };

    // 后端按 event: <kind> 命名，统一监听这几类
    ["step", "info", "warn", "error", "done"].forEach((k) =>
      es.addEventListener(k, onMsg as EventListener),
    );

    es.onerror = () => {
      // 流结束或网络断开；若未正常 done 也置为结束，避免一直转圈
      setFinished(true);
      es.close();
    };

    return () => es.close();
  }, [taskId]);

  return { events, finished, doneData };
}
