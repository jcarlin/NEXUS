export const ENTITY_COLORS: Record<string, string> = {
  person: "var(--color-entity-person)",
  organization: "var(--color-entity-org)",
  location: "var(--color-entity-location)",
  date: "var(--color-entity-date)",
  monetary_amount: "var(--color-entity-money)",
  // Legacy uppercase aliases
  PERSON: "var(--color-entity-person)",
  ORG: "var(--color-entity-org)",
  LOCATION: "var(--color-entity-location)",
  DATE: "var(--color-entity-date)",
  MONEY: "var(--color-entity-money)",
  DEFAULT: "var(--color-entity-default)",
};

export function entityColor(type: string): string {
  return ENTITY_COLORS[type] ?? ENTITY_COLORS[type.toLowerCase()] ?? ENTITY_COLORS.DEFAULT!;
}
