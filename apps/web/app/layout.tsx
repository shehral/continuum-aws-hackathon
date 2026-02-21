import type { Metadata } from "next"
import { Instrument_Sans, JetBrains_Mono } from "next/font/google"
import "./globals.css"
import { Providers } from "./providers"
import { DatadogInit } from "@/lib/datadog"

const instrumentSans = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
})

export const metadata: Metadata = {
  title: "Continuum - Knowledge Management Platform",
  description: "Capture, organize, and transfer engineering knowledge",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning className={`${instrumentSans.variable} ${jetbrainsMono.variable}`}>
      <body className="font-sans antialiased">
        <DatadogInit />
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
