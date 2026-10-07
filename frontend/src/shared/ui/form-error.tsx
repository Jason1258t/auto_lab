import { Alert, AlertDescription } from './alert'

/** An error text from the API, or nothing. */
export function FormError({ error }: { error: string | null | undefined }) {
  if (!error) return null
  return (
    <Alert variant="destructive">
      <AlertDescription>{error}</AlertDescription>
    </Alert>
  )
}
