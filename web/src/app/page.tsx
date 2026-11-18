import type { Metadata } from "next";
import "@/components/landing/landing.css";
import { ScrollProgress } from "@/components/landing/fx";
import { LandingNav } from "@/components/landing/landing-nav";
import {
  Anatomy, Audience, Changes, Closing, Compare, Drift, Faq, Features, Footer, Hero, Honest, How, Industries, Problem, Safety, Scores, Technology, Tour, Walkthrough,
} from "@/components/landing/sections";

export const metadata: Metadata = {
  title: "EvalGuard AI: a smoke alarm for AI chatbots",
  description:
    "EvalGuard asks your document-reading chatbot the same test questions again and again, has a second AI mark every answer, and warns you when quality slips.",
};

export default function Home() {
  return (
    <>
      <div className="aurora" aria-hidden><i /><i /><i /></div>
      <ScrollProgress />
      <LandingNav />
      <main>
        <Hero />
        <Problem />
        <How />
        <Tour />
        <Anatomy />
        <Features />
        <Scores />
        <Drift />
        <Changes />
        <Safety />
        <Industries />
        <Walkthrough />
        <Technology />
        <Audience />
        <Compare />
        <Honest />
        <Faq />
        <Closing />
      </main>
      <Footer />
    </>
  );
}
