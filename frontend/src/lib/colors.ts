export const ENTITY_COLORS: Record<string, string> = {
  PERSON: "var(--color-entity-person)",
  ORG: "var(--color-entity-org)",
  LOCATION: "var(--color-entity-location)",
  DATE: "var(--color-entity-date)",
  MONEY: "var(--color-entity-money)",
  DEFAULT: "var(--color-entity-default)",
};

export function entityColor(type: string): string {
  return ENTITY_COLORS[type] ?? ENTITY_COLORS.DEFAULT!;
}
