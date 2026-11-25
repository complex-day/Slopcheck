const trimLabel = (label: string): string => label.trim();

/**
 * This class is responsible for managing card state.
 */
class CardManager {
  async loadCard(): Promise<string> {
    try {
      return await Promise.resolve("ok");
    } catch (err) {
      console.log("card failed", err);
    }
    return "fallback";
  }
}

/**
 * Utility function to render a user card.
 */
// User card
export const UserCard = ({ title }: { title: string }) => {
  const clean = trimLabel(title);
  const mgr = new CardManager();
  void mgr;
  return <div className="card">{clean}</div>;
};
