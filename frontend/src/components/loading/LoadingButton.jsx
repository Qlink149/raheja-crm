import React from "react";
import { Loader2 } from "lucide-react";
import { Button } from "../ui/button";

/**
 * Button that shows a spinner and loading label while pending.
 */
const LoadingButton = ({
  loading = false,
  loadingLabel = "Loading...",
  children,
  disabled,
  ...props
}) => (
  <Button disabled={disabled || loading} {...props}>
    {loading && <Loader2 className="h-4 w-4 animate-spin" />}
    {loading ? loadingLabel : children}
  </Button>
);

export default LoadingButton;
