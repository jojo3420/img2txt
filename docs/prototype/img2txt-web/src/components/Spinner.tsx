import { Loader2 } from "lucide-react";

export default function Spinner({ size = 20 }: { size?: number }) {
  return <Loader2 size={size} className="animate-spin text-accent-500" />;
}
