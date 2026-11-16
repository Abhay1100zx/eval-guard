import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "EvalGuard AI",
  description: "Multi-domain RAG evaluation, benchmarking and drift detection",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full">
        <ClerkProvider
          appearance={{
            variables: {
              colorPrimary: "#7a7aff",
              borderRadius: "0.9rem",
            },
            elements: {
              cardBox: "glass-strong !rounded-[1.75rem] !shadow-none !border",
              card: "!bg-transparent !shadow-none",
              footer: "!bg-transparent",
              footerAction: "!bg-transparent",
              formButtonPrimary: "btn-primary btn-spring !rounded-full",
              socialButtonsBlockButton: "glass-inset !rounded-2xl",
            },
          }}
        >
          {children}
        </ClerkProvider>
      </body>
    </html>
  );
}
