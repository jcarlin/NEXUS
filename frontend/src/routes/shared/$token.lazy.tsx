import { createLazyFileRoute } from "@tanstack/react-router";
import { SharedChatViewer } from "@/components/shared/shared-chat-viewer";

export const Route = createLazyFileRoute("/shared/$token")({
  component: SharedChatPage,
});

function SharedChatPage() {
  const { token } = Route.useParams();
  return <SharedChatViewer token={token} />;
}
