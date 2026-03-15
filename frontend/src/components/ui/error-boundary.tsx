import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "./button";

function isChunkLoadError(error: Error): boolean {
  return (
    error.name === "TypeError" &&
    (error.message.includes("Failed to fetch dynamically imported module") ||
      error.message.includes("error loading dynamically imported module") ||
      error.message.includes("Importing a module script failed"))
  );
}

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      const chunkError =
        this.state.error != null && isChunkLoadError(this.state.error);

      if (chunkError) {
        return (
          <div className="flex flex-col items-center justify-center gap-4 rounded-md border border-blue-500/30 bg-blue-500/5 p-8 text-center">
            <RefreshCw className="h-10 w-10 text-blue-500" />
            <div>
              <h3 className="text-lg font-semibold">
                A new version is available
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                The app has been updated. Reload to get the latest version.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.location.reload()}
            >
              Reload Page
            </Button>
          </div>
        );
      }

      return (
        <div className="flex flex-col items-center justify-center gap-4 rounded-md border border-destructive/30 bg-destructive/5 p-8 text-center">
          <AlertCircle className="h-10 w-10 text-destructive" />
          <div>
            <h3 className="text-lg font-semibold">Something went wrong</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {this.state.error?.message ?? "An unexpected error occurred."}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            Try Again
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
