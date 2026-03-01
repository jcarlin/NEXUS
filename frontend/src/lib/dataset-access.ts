/**
 * Pure utility functions for dataset access control logic.
 * No React dependencies — fully testable in isolation.
 */

/**
 * Returns true if the given role is allowed to manage dataset access.
 * Matches the backend `require_role("admin", "attorney")` on access endpoints.
 */
export function canManageDatasetAccess(
  role: string | undefined | null,
): boolean {
  return role === "admin" || role === "attorney";
}

/**
 * Filters a list of users to exclude those who already have an access grant.
 * Used by the user picker in the access control dialog.
 */
export function filterAvailableUsers<
  U extends { id: string },
  A extends { user_id: string },
>(allUsers: U[], grantedAccess: A[]): U[] {
  const grantedIds = new Set(grantedAccess.map((a) => a.user_id));
  return allUsers.filter((u) => !grantedIds.has(u.id));
}
