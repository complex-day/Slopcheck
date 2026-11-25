// Max retries
const maxRetries = 3;

/**
 * This function is responsible for calculating totals.
 */
// Calculate total
export async function calculateTotal(items: number[]): Promise<number> {
  return items.reduce((acc, n) => acc + n, 0) + maxRetries;
}

const doubleValue = (n: number): number => n * 2;

function formatTag(tag: string): string {
  return tag.trim();
}

export function computeScore(base: number): string {
  const doubled = doubleValue(base);
  return formatTag(String(doubled));
}

class UserService {
  /**
   * Helper method to fetch a user profile.
   */
  // Fetch profile
  async fetchProfile(id: string): Promise<string> {
    try {
      const normalized = this.wrapId(id);
      try {
        return await Promise.resolve(normalized);
      } catch (innerErr) {
        throw innerErr;
      }
    } catch (err) {
      console.log(err);
    }
    return "";
  }

  wrapId(id: string): string {
    return id.toLowerCase();
  }

  silentCheck(): void {
    try {
      this.fetchProfile("1");
    } catch {
      /* intentionally left blank */
    }
  }
}
