import { Input } from './input'
import { Label } from './label'
import { Textarea } from './textarea'

/** A label, an input (or a textarea) and an optional hint under it. */
export function FormField(props: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
  hint?: string
  autoComplete?: string
  multiline?: boolean
  required?: boolean
  maxLength?: number
}) {
  const shared = {
    id: props.id,
    value: props.value,
    maxLength: props.maxLength,
    required: props.required ?? true,
    'aria-describedby': props.hint ? `${props.id}-hint` : undefined,
  }
  return (
    <div className="grid gap-2">
      <Label htmlFor={props.id}>{props.label}</Label>
      {props.multiline ? (
        <Textarea {...shared} onChange={(e) => props.onChange(e.target.value)} />
      ) : (
        <Input
          {...shared}
          type={props.type ?? 'text'}
          autoComplete={props.autoComplete}
          onChange={(e) => props.onChange(e.target.value)}
        />
      )}
      {props.hint && (
        <p id={`${props.id}-hint`} className="text-xs text-muted-foreground">
          {props.hint}
        </p>
      )}
    </div>
  )
}
