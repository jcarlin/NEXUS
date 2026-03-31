import { useCallback, useState } from "react";
import { createRootRoute, Outlet, useMatches } from "@tanstack/react-router";
import { Menu } from "lucide-react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { AuthGuard } from "@/components/layout/auth-guard";
import { CommandPalette } from "@/components/layout/command-palette";
import { DefinedTermsSidebar } from "@/components/layout/defined-terms-sidebar";
import { KeyboardShortcutsDialog } from "@/components/ui/keyboard-shortcuts-dialog";
// Tour disabled — users can trigger manually from help menu
// const OnboardingTour = lazy(() =>
//   import("@/components/onboarding/tour").then(m => ({ default: m.OnboardingTour }))
// );
import { useKeyboardShortcuts } from "@/hooks/use-keyboard-shortcuts";

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  const matches = useMatches();
  const isLoginPage = matches.some((m) => m.routeId === "/login");
  const isSharedPage = matches.some((m) => m.routeId.startsWith("/shared"));
  const [commandOpen, setCommandOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const openCommandPalette = useCallback(() => setCommandOpen(true), []);
  const { shortcutsHelpOpen, setShortcutsHelpOpen } = useKeyboardShortcuts({
    onOpenCommandPalette: openCommandPalette,
  });

  if (isLoginPage || isSharedPage) {
    return <Outlet />;
  }

  return (
    <TooltipProvider delayDuration={200}>
      <AuthGuard>
        <div className="flex h-screen overflow-hidden">
          {/* Desktop sidebar */}
          <div className="hidden xl:block">
            <Sidebar />
          </div>

          <div className="flex flex-1 flex-col overflow-hidden">
            {/* Mobile sidebar drawer — trigger is inside the header flow */}
            <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
              <Header
                mobileNavTrigger={
                  <SheetTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="shrink-0 xl:hidden"
                    >
                      <Menu className="h-5 w-5" />
                    </Button>
                  </SheetTrigger>
                }
              />
              <SheetContent side="left" className="w-56 p-0" overlayClassName="bg-black/20">
                <SheetTitle className="sr-only">Navigation</SheetTitle>
                <SheetDescription className="sr-only">Main navigation menu</SheetDescription>
                <Sidebar />
              </SheetContent>
            </Sheet>
            <main className="flex-1 overflow-auto p-4 md:p-6">
              <ErrorBoundary>
                <Outlet />
              </ErrorBoundary>
            </main>
          </div>
          <DefinedTermsSidebar />
        </div>
        <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
        <KeyboardShortcutsDialog open={shortcutsHelpOpen} onOpenChange={setShortcutsHelpOpen} />
        {/* Tour disabled — users can trigger manually from help menu */}
      </AuthGuard>
    </TooltipProvider>
  );
}
