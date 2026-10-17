import { useCallback, useEffect, useState, type ReactNode } from "react";
import useEmblaCarousel from "embla-carousel-react";
import Autoplay from "embla-carousel-autoplay";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { usePrefs } from "@/store/prefs";

/**
 * Generic Embla carousel.
 *   <Carousel slideClass="basis-full sm:basis-1/2 lg:basis-1/3" autoplay>{cards}</Carousel>
 */
export function Carousel({
  children,
  slideClass = "basis-full",
  autoplay = false,
  delay = 4500,
  loop = true,
  arrows = true,
  dots = true,
  gap = "gap-5",
  className,
  arrowsPosition = "sides",
}: {
  children: ReactNode[];
  slideClass?: string;
  autoplay?: boolean;
  delay?: number;
  loop?: boolean;
  arrows?: boolean;
  dots?: boolean;
  gap?: string;
  className?: string;
  arrowsPosition?: "sides" | "top";
}) {
  const rtl = usePrefs((s) => s.lang === "ur");
  const [ref, api] = useEmblaCarousel(
    { loop, align: "start", direction: rtl ? "rtl" : "ltr", skipSnaps: false },
    autoplay ? [Autoplay({ delay, stopOnInteraction: false, stopOnMouseEnter: true })] : [],
  );
  const [index, setIndex] = useState(0);
  const [snaps, setSnaps] = useState<number[]>([]);

  const onSelect = useCallback(() => {
    if (!api) return;
    setIndex(api.selectedScrollSnap());
  }, [api]);

  useEffect(() => {
    if (!api) return;
    setSnaps(api.scrollSnapList());
    onSelect();
    api.on("select", onSelect);
    api.on("reInit", () => {
      setSnaps(api.scrollSnapList());
      onSelect();
    });
    return () => {
      api.off("select", onSelect);
    };
  }, [api, onSelect]);

  const arrowBtn = "flex h-10 w-10 items-center justify-center rounded-full bg-white/90 text-brand-800 shadow-soft ring-1 ring-black/5 backdrop-blur transition hover:bg-white hover:scale-105 dark:bg-brand-900/90 dark:text-white";

  return (
    <div className={cn("relative", className)}>
      {arrows && arrowsPosition === "top" && (
        <div className="absolute -top-16 end-0 hidden gap-2 sm:flex">
          <button className={arrowBtn} onClick={() => api?.scrollPrev()} aria-label="Previous">
            <ChevronLeft className="h-5 w-5 rtl:rotate-180" />
          </button>
          <button className={arrowBtn} onClick={() => api?.scrollNext()} aria-label="Next">
            <ChevronRight className="h-5 w-5 rtl:rotate-180" />
          </button>
        </div>
      )}
      <div className="overflow-hidden" ref={ref}>
        <div className={cn("flex", gap)}>
          {children.map((c, i) => (
            <div key={i} className={cn("min-w-0 shrink-0 grow-0", slideClass)}>
              {c}
            </div>
          ))}
        </div>
      </div>
      {arrows && arrowsPosition === "sides" && snaps.length > 1 && (
        <>
          <button className={cn(arrowBtn, "absolute start-2 top-1/2 -translate-y-1/2")} onClick={() => api?.scrollPrev()} aria-label="Previous">
            <ChevronLeft className="h-5 w-5 rtl:rotate-180" />
          </button>
          <button className={cn(arrowBtn, "absolute end-2 top-1/2 -translate-y-1/2")} onClick={() => api?.scrollNext()} aria-label="Next">
            <ChevronRight className="h-5 w-5 rtl:rotate-180" />
          </button>
        </>
      )}
      {dots && snaps.length > 1 && (
        <div className="mt-5 flex justify-center gap-1.5">
          {snaps.map((_, i) => (
            <button
              key={i}
              onClick={() => api?.scrollTo(i)}
              aria-label={`Go to slide ${i + 1}`}
              className={cn("h-2 rounded-full transition-all", i === index ? "w-6 bg-brand-700" : "w-2 bg-brand-200 dark:bg-white/20")}
            />
          ))}
        </div>
      )}
    </div>
  );
}
