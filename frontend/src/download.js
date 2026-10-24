// Saves a downloaded file to the user's computer.
// The page fetched the file itself (so it can show a clear message if the API is down or rejects the request), and
// now hands the bytes to the browser the same way a normal download link would: a temporary address for the file,
// a link click, and then clean-up.
export function saveFile(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Free the temporary address a moment later (freeing it at once can cancel the download in some browsers).
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
