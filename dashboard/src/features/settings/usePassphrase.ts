import { useState } from "react";
import { MIN_PASSPHRASE } from "../../lib/constants";

export type PassphraseState = ReturnType<typeof usePassphrase>;

/** Passphrase + confirmation for creating encrypted exports. */
export function usePassphrase() {
  const [passphrase, setPassphrase] = useState("");
  const [confirm, setConfirm] = useState("");
  const tooShort = passphrase.length > 0 && passphrase.length < MIN_PASSPHRASE;
  const mismatch = confirm.length > 0 && confirm !== passphrase;
  const valid = passphrase.length >= MIN_PASSPHRASE && confirm === passphrase;
  return {
    passphrase,
    confirm,
    setPassphrase,
    setConfirm,
    tooShort,
    mismatch,
    valid,
    reset: () => {
      setPassphrase("");
      setConfirm("");
    },
  };
}
