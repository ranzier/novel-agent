import { useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { ProgressDrawer } from "../components/ProgressDrawer";
import { DeleteBookModal } from "../components/DeleteBookModal";
import { OverviewTab } from "./tabs/OverviewTab";
import { BibleTab } from "./tabs/BibleTab";
import { CharactersTab } from "./tabs/CharactersTab";
import { OutlineTab } from "./tabs/OutlineTab";
import { ChaptersTab } from "./tabs/ChaptersTab";
import { ReviewsTab } from "./tabs/ReviewsTab";

const TABS = [
  { key: "overview", label: "概览" },
  { key: "bible", label: "设定圣经" },
  { key: "characters", label: "角色库" },
  { key: "outline", label: "大纲" },
  { key: "chapters", label: "章节" },
  { key: "reviews", label: "校验/记忆" },
];

export interface RunningTask {
  id: string;
  title: string;
}

export function Workspace() {
  const { slug = "" } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [tab, setTab] = useState("overview");
  const [task, setTask] = useState<RunningTask | null>(null);
  const [showDelete, setShowDelete] = useState(false);

  const { data: ov } = useQuery({
    queryKey: ["overview", slug],
    queryFn: () => api.overview(slug),
  });

  const startTask = (id: string, title: string) => setTask({ id, title });

  return (
    <div className="workspace">
      <div className="sidebar">
        <Link to="/" className="muted" style={{ fontSize: 13 }}>
          ← 所有项目
        </Link>
        <h3 style={{ marginTop: 12 }}>{ov?.title ?? slug}</h3>
        <div className="muted" style={{ fontSize: 12, marginBottom: 16 }}>
          {ov?.genre} · {ov?.progress.written}/{ov?.progress.total} 章
        </div>
        {TABS.map((t) => (
          <div
            key={t.key}
            className={`nav-item ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </div>
        ))}
        <div
          className="nav-item"
          onClick={() => setShowDelete(true)}
          style={{ marginTop: "auto", color: "var(--red)" }}
        >
          🗑 删除本书
        </div>
      </div>

      <div className="content">
        {tab === "overview" && <OverviewTab slug={slug} onTask={startTask} />}
        {tab === "bible" && <BibleTab slug={slug} />}
        {tab === "characters" && <CharactersTab slug={slug} />}
        {tab === "outline" && <OutlineTab slug={slug} onTask={startTask} />}
        {tab === "chapters" && <ChaptersTab slug={slug} onTask={startTask} />}
        {tab === "reviews" && <ReviewsTab slug={slug} />}
      </div>

      {task && (
        <ProgressDrawer
          taskId={task.id}
          title={task.title}
          onClose={() => setTask(null)}
          onDone={() => {
            qc.invalidateQueries();
          }}
        />
      )}

      {showDelete && (
        <DeleteBookModal
          title={ov?.title ?? slug}
          onClose={() => setShowDelete(false)}
          onConfirm={async () => {
            await api.deleteBook(slug);
            qc.invalidateQueries({ queryKey: ["books"] });
            navigate("/");
          }}
        />
      )}
    </div>
  );
}
