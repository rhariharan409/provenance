/**
 * Safe date formatting helpers that handle null, undefined, invalid dates,
 * and strings without throwing RangeError: Invalid time value.
 */

/**
 * Returns "—" for null, undefined, empty string, or invalid date values.
 * Otherwise returns a UTC YYYY-MM-DD string.
 */
export function formatDate(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const d = new Date(value as string | number | Date);
  if (isNaN(d.getTime())) {
    return "—";
  }
  return d.toISOString().slice(0, 10);
}

/**
 * Returns "—" for null, undefined, empty string, or invalid date values.
 * Otherwise returns a UTC YYYY-MM-DD HH:MM UTC string.
 */
export function formatDateTime(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const d = new Date(value as string | number | Date);
  if (isNaN(d.getTime())) {
    return "—";
  }
  return d.toISOString().replace("T", " ").replace(/\..+/, " UTC");
}

