/**
 * Tiny class-joiner (no clsx dependency). Filters falsy tokens.
 */
export type ClassValue = string | number | null | undefined | false;

export function cn(...values: ClassValue[]): string {
  const out: string[] = [];
  for (const v of values) {
    if (v) out.push(String(v));
  }
  return out.join(' ');
}
