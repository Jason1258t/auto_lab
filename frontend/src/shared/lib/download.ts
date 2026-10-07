/** Save a blob as a file. Needed because downloads go through the API
 *  client (the access token is in memory, a plain link cannot send it). */
export function saveBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  URL.revokeObjectURL(url)
}
