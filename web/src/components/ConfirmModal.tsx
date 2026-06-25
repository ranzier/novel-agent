// 通用确认弹窗：用于需要二次确认的操作。

export function ConfirmModal({
  title,
  message,
  confirmText = "确定",
  cancelText = "取消",
  busy = false,
  busyText = "处理中…",
  onConfirm,
  onClose,
}: {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  busy?: boolean;
  busyText?: string;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <div className="drawer-mask" onClick={busy ? undefined : onClose}>
      <div
        className="card"
        style={{ width: 380, margin: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0 }}>{title}</h3>
        <div
          className="muted"
          style={{ fontSize: 13, lineHeight: 1.7, marginBottom: 18 }}
        >
          {message}
        </div>
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button onClick={onClose} disabled={busy}>
            {cancelText}
          </button>
          <button className="primary" onClick={onConfirm} disabled={busy}>
            {busy ? busyText : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
