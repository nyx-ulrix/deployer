import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { cn } from "../../lib/cn";

const control =
  "w-full min-w-0 rounded-lg border border-border bg-surface text-fg placeholder:text-muted/70 shadow-xs " +
  "focus:border-accent focus:outline-none focus:ring-3 focus:ring-ring disabled:opacity-60 " +
  "aria-[invalid=true]:border-danger";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest },
  ref,
) {
  return <input ref={ref} className={cn(control, "h-10 px-3 text-base sm:text-sm", className)} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...rest }, ref) {
    return (
      <textarea ref={ref} className={cn(control, "min-h-24 px-3 py-2 text-base sm:text-sm", className)} {...rest} />
    );
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...rest },
  ref,
) {
  return (
    <select ref={ref} className={cn(control, "h-10 pr-8 pl-3 text-base sm:text-sm", className)} {...rest}>
      {children}
    </select>
  );
});

type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: ReactNode;
  description?: ReactNode;
};

export function Checkbox({ label, description, className, id, ...rest }: CheckboxProps) {
  const autoId = useId();
  const cid = id ?? autoId;
  return (
    <label htmlFor={cid} className={cn("flex items-start gap-2.5 text-sm", className)}>
      <input id={cid} type="checkbox" className="mt-0.5 size-4 shrink-0 accent-[var(--accent)]" {...rest} />
      <span className="min-w-0">
        <span className="font-medium">{label}</span>
        {description && <span className="mt-0.5 block text-xs text-muted">{description}</span>}
      </span>
    </label>
  );
}

type FieldProps = {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  children: (id: string) => ReactNode;
  className?: string;
  optional?: boolean;
};

/** Label + control + hint/error. `children` receives the generated id for the control. */
export function Field({ label, hint, error, children, className, optional }: FieldProps) {
  const id = useId();
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm font-medium">
        {label}
        {optional && <span className="ml-1 font-normal text-muted">(optional)</span>}
      </label>
      {children(id)}
      {error ? (
        <p className="text-xs text-danger">{error}</p>
      ) : hint ? (
        <p className="text-xs text-muted">{hint}</p>
      ) : null}
    </div>
  );
}
