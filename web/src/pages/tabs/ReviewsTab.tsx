import { useQuery } from "@tanstack/react-query";
import { api } from "../../api";

export function ReviewsTab({ slug }: { slug: string }) {
  const { data: reviews } = useQuery({
    queryKey: ["reviews", slug],
    queryFn: () => api.reviews(slug),
  });
  const { data: state } = useQuery({
    queryKey: ["state", slug],
    queryFn: () => api.state(slug),
  });
  const { data: ov } = useQuery({
    queryKey: ["overview", slug],
    queryFn: () => api.overview(slug),
  });
  const progLabel = ov?.progression_label || "状态";

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
      <div>
        <h2 style={{ marginTop: 0 }}>一致性校验</h2>
        {reviews?.length === 0 && <p className="muted">暂无校验记录。</p>}
        {reviews?.map((r) => {
          const issues = r.issues ?? [];
          const errs = issues.filter((i: any) => i.severity === "error");
          const warns = issues.filter((i: any) => i.severity === "warn");
          return (
            <div key={r.chapter} className="card" style={{ marginBottom: 10 }}>
              <div className="spread">
                <strong>第 {r.chapter} 章</strong>
                {issues.length === 0 ? (
                  <span className="tag ok">通过</span>
                ) : (
                  <span>
                    {errs.length > 0 && (
                      <span className="tag err">{errs.length} 硬伤</span>
                    )}{" "}
                    {warns.length > 0 && (
                      <span className="tag warn">{warns.length} 疑点</span>
                    )}
                  </span>
                )}
              </div>
              {issues.map((i: any, k: number) => (
                <div
                  key={k}
                  style={{ fontSize: 13, marginTop: 6 }}
                  className={i.severity === "error" ? "" : "muted"}
                >
                  <span
                    className={`tag ${i.severity === "error" ? "err" : "warn"}`}
                  >
                    {i.category}
                  </span>{" "}
                  {i.message}
                </div>
              ))}
            </div>
          );
        })}
      </div>

      <div>
        <h2 style={{ marginTop: 0 }}>世界状态（记忆）</h2>
        <div className="card">
          <p>
            <span className="muted">主角{progLabel}：</span>
            {state?.protagonist_tier || "—"}
          </p>
          <p>
            <span className="muted">主角位置：</span>
            {state?.protagonist_location || "—"}
          </p>
          <div className="muted" style={{ marginTop: 10 }}>
            未回收伏笔
          </div>
          <ul>
            {(state?.foreshadowing ?? []).map((f: any, i: number) => (
              <li key={i}>{typeof f === "string" ? f : f.content ?? ""}</li>
            ))}
          </ul>
          <div className="muted">角色状态</div>
          <ul>
            {(state?.characters ?? []).map((c: any, i: number) => (
              <li key={i}>
                {c.name} · {c.power_tier || "—"}{" "}
                {c.status === "死亡" && <span className="tag err">死亡</span>}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
