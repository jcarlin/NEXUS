import type { Step } from "react-joyride";

export const dashboardSteps: Step[] = [
  {
    target: "[data-tour='sidebar-nav']",
    content:
      "Navigate between modules using the sidebar. Access documents, entities, analytics, and review tools from here.",
    placement: "right",
    disableBeacon: true,
  },
  {
    target: "[data-tour='matter-selector']",
    content:
      "Select the active matter (case) to scope all data. Every query, document list, and entity view is filtered to the selected matter.",
    placement: "bottom",
    disableBeacon: true,
  },
  {
    target: "[data-tour='stat-cards']",
    content:
      "At-a-glance metrics for your investigation: total documents, extracted entities, flagged hot docs, and active processing jobs.",
    placement: "bottom",
    disableBeacon: true,
  },
  {
    target: "[data-tour='recent-activity']",
    content:
      "Recent activity, pipeline status, and knowledge graph overview. Monitor ingestion progress and explore entity relationships.",
    placement: "top",
    disableBeacon: true,
  },
];
