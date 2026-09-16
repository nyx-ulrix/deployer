import { Field, Input } from "../../components/ui/Input";
import { MIN_PASSPHRASE } from "../../lib/constants";
import type { PassphraseState } from "./usePassphrase";

export function PassphraseFields({ state }: { state: PassphraseState }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field
        label="Passphrase"
        hint={`At least ${MIN_PASSPHRASE} characters. You'll need it to import the file — it can't be recovered.`}
        error={state.tooShort ? `Use at least ${MIN_PASSPHRASE} characters.` : undefined}
      >
        {(id) => (
          <Input
            id={id}
            type="password"
            autoComplete="new-password"
            value={state.passphrase}
            aria-invalid={state.tooShort}
            onChange={(e) => state.setPassphrase(e.target.value)}
          />
        )}
      </Field>
      <Field label="Confirm passphrase" error={state.mismatch ? "Passphrases don't match." : undefined}>
        {(id) => (
          <Input
            id={id}
            type="password"
            autoComplete="new-password"
            value={state.confirm}
            aria-invalid={state.mismatch}
            onChange={(e) => state.setConfirm(e.target.value)}
          />
        )}
      </Field>
    </div>
  );
}
