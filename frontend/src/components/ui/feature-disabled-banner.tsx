import { Info } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface FeatureDisabledBannerProps {
  featureName: string;
}

export function FeatureDisabledBanner({
  featureName,
}: FeatureDisabledBannerProps) {
  return (
    <Alert>
      <Info className="h-4 w-4" />
      <AlertDescription>
        This feature requires <strong>{featureName}</strong> to be enabled.
        Contact your administrator.
      </AlertDescription>
    </Alert>
  );
}
