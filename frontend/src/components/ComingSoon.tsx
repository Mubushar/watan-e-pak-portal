import { Construction } from "lucide-react";
import { EmptyState } from "@/components/ui";

/** Temporary placeholder while a page is being built. */
export function ComingSoon({ title }: { title: string }) {
  return (
    <div className="container py-16">
      <EmptyState icon={<Construction className="h-6 w-6" />} title={title} hint="This screen is being built." />
    </div>
  );
}
