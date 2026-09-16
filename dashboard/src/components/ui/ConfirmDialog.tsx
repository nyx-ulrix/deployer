import { useState, type ReactNode } from "react";
import { Button } from "./Button";
import { Dialog } from "./Dialog";
import { Input } from "./Input";

export type ConfirmDialogProps = {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<unknown>;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  confirmLabel?: string;
  /** When set, the user must type this exact text to enable the confirm button. */
  confirmText?: string;
  destructive?: boolean;
  loading?: boolean;
};

export function ConfirmDialog(props: ConfirmDialogProps) {
  if (!props.open) return null;
  // Mount the inner component only while open so the typed text resets each time.
  return <ConfirmDialogInner {...props} />;
}

function ConfirmDialogInner({
  open,
  onClose,
  onConfirm,
  title,
  description,
  children,
  confirmLabel = "Confirm",
  confirmText,
  destructive = true,
  loading = false,
}: ConfirmDialogProps) {
  const [typed, setTyped] = useState("");
  const matches = !confirmText || typed.trim() === confirmText;
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      dismissible={!loading}
      footer={
        <>
          <Button onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button
            variant={destructive ? "danger" : "primary"}
            disabled={!matches}
            loading={loading}
            onClick={() => void onConfirm()}
            data-autofocus={confirmText ? undefined : true}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <form
        className="space-y-3 text-sm"
        onSubmit={(e) => {
          e.preventDefault();
          if (matches && !loading) void onConfirm();
        }}
      >
        {description && <div className="text-muted">{description}</div>}
        {children}
        {confirmText && (
          <div className="space-y-1.5">
            <label className="block text-sm">
              Type <code className="rounded bg-surface-2 px-1 py-0.5 font-mono font-semibold">{confirmText}</code> to
              confirm
            </label>
            <Input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              aria-label={`Type ${confirmText} to confirm`}
            />
          </div>
        )}
      </form>
    </Dialog>
  );
}
