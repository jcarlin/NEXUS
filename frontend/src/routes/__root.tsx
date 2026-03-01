import { useState } from "react";
import { createRootRoute, Outlet, useMatches } from "@tanstack/react-router";
import { Menu } from "lucide-react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { AuthGuard } from "@/components/layout/auth-guard";
import { CommandPalette } from "@/components/layout/command-palette";
import { DefinedTermsSidebar } from "@/components/layout/defined-terms-sidebar";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard-shortcuts";

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  const matches = useMatches();
  const isLoginPage = matches.some((m) => m.routeId === "/login");
  const [commandOpen, setCommandOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useKeyboardShortcuts({
    onOpenCommandPalette: () => setCommandOpen(true),
  });

  if (isLoginPage) {
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

          {/* Mobile sidebar drawer */}
          <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
            <SheetTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="fixed left-3 top-3 z-40 xl:hidden"
              >
                <Menu className="h-5 w-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-56 p-0">
              <Sidebar />
            </SheetContent>
          </Sheet>

          <div className="flex flex-1 flex-col overflow-hidden">
            <Header />
            <main className="flex-1 overflow-auto p-4 md:p-6">
              <ErrorBoundary>
                <Outlet />
              </ErrorBoundary>
            </main>
          </div>
          <DefinedTermsSidebar />
        </div>
        <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
      </AuthGuard>
    </TooltipProvider>
  );
}
