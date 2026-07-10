import { useState } from "react";
import SiteHeader from "../components/landing/SiteHeader";
import SiteFooter from "../components/landing/SiteFooter";
import Hero from "../components/landing/Hero";
import ProblemSection from "../components/landing/ProblemSection";
import Differentiators from "../components/landing/Differentiators";
import HowItWorks from "../components/landing/HowItWorks";
import ResultsShowcase from "../components/landing/ResultsShowcase";
import Pricing from "../components/landing/Pricing";
import Faq from "../components/landing/Faq";
import CtaBanner from "../components/landing/CtaBanner";
import IntentModal from "../components/IntentModal";
import type { IntentRequest } from "../api/types";

export default function LandingPage() {
  const [intentPlan, setIntentPlan] = useState<IntentRequest["plan"] | null>(null);

  const openIntent = () => setIntentPlan("subscription");

  return (
    <div className="min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1">
        <Hero onOpenIntent={openIntent} />
        <ProblemSection />
        <Differentiators />
        <HowItWorks />
        <ResultsShowcase />
        <Pricing onOpenIntent={openIntent} />
        <Faq />
        <CtaBanner onOpenIntent={openIntent} />
      </main>
      <SiteFooter />

      {intentPlan && (
        <IntentModal plan={intentPlan} onClose={() => setIntentPlan(null)} />
      )}
    </div>
  );
}
