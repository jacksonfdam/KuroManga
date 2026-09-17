/** Guards an operator-supplied address before it becomes the start of an href.
 *
 * `komga_public_url` is editable in Settings and the series screens paste it
 * straight into a link. React escapes text but does not refuse a scheme:
 * `javascript:` in an href runs when the link is clicked, and the path a
 * template appends after it is trivially commented out, so the template around
 * it protects nothing.
 *
 * `routes_settings.py` refuses those on write, which is the real fix. This is
 * the half that covers a value stored before that check existed, and it means
 * a component is safe without knowing who filled the field.
 */
const FETCHABLE = new Set(['http:', 'https:'])

export function externalBase(value: string | null | undefined): string {
  if (!value) return ''
  let parsed: URL
  try {
    parsed = new URL(value)
  } catch {
    // Not an absolute URL at all. A bare host cannot be linked to anyway, so
    // there is nothing to salvage by guessing a scheme for it.
    return ''
  }
  if (!FETCHABLE.has(parsed.protocol)) return ''
  // Trailing slashes are stripped because every caller appends its own path,
  // and `//book/1` reads as a protocol-relative URL to a host called "book".
  return value.replace(/\/+$/, '')
}
