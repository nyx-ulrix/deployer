import { useState } from "react";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Field, Input } from "../../components/ui/Input";
import { splitFolderName } from "./notebook";

type Props = {
  open: boolean;
  title: string;
  confirmLabel: string;
  initialName?: string;
  initialFolder?: string | null;
  loading?: boolean;
  onClose: () => void;
  onSubmit: (name: string, folder: string | null) => void;
};

/** Name + folder of a snippet (first save, "Save as…", rename). Typing `folder/name` as the name splits it. */
export function SnippetDialog(props: Props) {
  if (!props.open) return null;
  // Mount the form only while open so the fields reset each time.
  return <SnippetForm {...props} />;
}

function SnippetForm({ open, title, confirmLabel, initialName = "", initialFolder = null, loading = false, onClose, onSubmit }: Props) {
  const [name, setName] = useState(initialName);
  const [folder, setFolder] = useState(initialFolder ?? "");
  const parsed = splitFolderName(name, folder);
  const valid = parsed.name.length > 0 && parsed.name.length <= 120 && (parsed.folder?.length ?? 0) <= 120;
  const submit = () => {
    if (valid && !loading) onSubmit(parsed.name, parsed.folder);
  };
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
          <Button variant="primary" onClick={submit} disabled={!valid} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <Field label="Name" hint="Type folder/name to file it in a folder.">
          {(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} maxLength={241} autoComplete="off" data-autofocus />}
        </Field>
        <Field label="Folder" optional>
          {(id) => <Input id={id} value={folder} onChange={(e) => setFolder(e.target.value)} maxLength={120} autoComplete="off" placeholder="No folder" />}
        </Field>
      </form>
    </Dialog>
  );
}
